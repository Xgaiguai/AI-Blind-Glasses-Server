"""
本地 ASR（CPU）：使用 faster-whisper 把 wav bytes 轉文字。

重點：
- lazy load 模型（避免啟動就吃資源）
- 允許用 ASR_WHISPER_MODEL_DIR 指向本地模型資料夾
- 兼容你韌體上傳的音訊：16kHz、16-bit、單聲道 wav（見 `firmware/include/config.h` 或韌體倉庫根之 `include/config.h`）
"""

from __future__ import annotations

import io
import os
import tempfile
import wave
from typing import Optional

import config

try:
    # faster-whisper
    from faster_whisper import WhisperModel  # type: ignore
except Exception:  # pragma: no cover
    WhisperModel = None  # type: ignore[assignment]


_model: Optional[object] = None
_model_loaded: bool = False
_warmup_done: bool = False


def _minimal_silence_wav_bytes(duration_sec: float = 0.05, sample_rate: int = 16000) -> bytes:
    """16-bit mono PCM WAV，與韌體錄音格式一致，供預熱用。"""
    n = max(1, int(sample_rate * duration_sec))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(b"\x00\x00" * n)
    return buf.getvalue()


def _get_whisper_cfg() -> dict:
    return {
        "model_size": getattr(config, "ASR_WHISPER_MODEL", "base"),
        "language": getattr(config, "ASR_WHISPER_LANG", "zh"),
        "device": getattr(config, "ASR_WHISPER_DEVICE", "cpu"),
        "compute_type": getattr(config, "ASR_WHISPER_COMPUTE_TYPE", "int8"),
        "model_dir": (getattr(config, "ASR_WHISPER_MODEL_DIR", "") or "").strip(),
    }


def _lazy_load_model() -> None:
    global _model, _model_loaded

    if _model_loaded:
        return
    if WhisperModel is None:
        _model_loaded = True
        _model = None
        return

    cfg = _get_whisper_cfg()
    model_size = cfg["model_size"]
    model_dir = cfg["model_dir"]

    # 若你已手動把模型放在本地資料夾，可用 model_dir 來避免模型下載（台灣網路可能不穩）
    local_files_only = bool(model_dir)
    download_root = model_dir if model_dir else None

    try:
        if download_root:
            _model = WhisperModel(
                model_size,
                device=cfg["device"],
                compute_type=cfg["compute_type"],
                download_root=download_root,
                local_files_only=local_files_only,
            )
        else:
            _model = WhisperModel(
                model_size,
                device=cfg["device"],
                compute_type=cfg["compute_type"],
            )
        _model_loaded = True
    except Exception:
        _model = None
        _model_loaded = True


def transcribe_wav_bytes(audio_wav_bytes: bytes) -> str:
    """
    :param audio_wav_bytes: wav bytes
    :return: transcript（失敗回空字串）
    """
    if not audio_wav_bytes:
        return ""

    _lazy_load_model()
    if _model is None:
        return ""

    cfg = _get_whisper_cfg()
    language = cfg["language"]

    # faster-whisper 主要吃檔案路徑；用 temp file 避免改韌體/保存永久檔案
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_wav_bytes)
            tmp_path = f.name

        # transcribe 回傳 (segments, info)
        segments, _info = _model.transcribe(
            tmp_path,
            language=language,
            vad_filter=True,
            beam_size=1,
            best_of=1,
        )
        text_parts = []
        for seg in segments:
            if getattr(seg, "text", None):
                text_parts.append(seg.text)
        return "".join(text_parts).strip()
    except Exception:
        return ""
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def warmup_whisper(duration_sec: float = 0.05) -> bool:
    """
    強制載入模型並跑一次極短轉寫，降低首次使用者語音延遲。
    """
    global _warmup_done
    if _warmup_done:
        return True
    try:
        transcribe_wav_bytes(_minimal_silence_wav_bytes(duration_sec=duration_sec))
    except Exception:
        pass
    _warmup_done = True
    return True

