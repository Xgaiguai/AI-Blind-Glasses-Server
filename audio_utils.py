"""
TTS 音檔產生 - 供 GET /audio/latest 回傳
"""
import io
import wave
import struct
import os

# 可選：使用 gTTS 產生中文語音（未安裝時改為 None，型別檢查可推斷使用時已繫結）
try:
    from gtts import gTTS  # type: ignore[import-untyped]
    HAS_GTTS = True
except ImportError:
    HAS_GTTS = False
    gTTS = None  # 未安裝時讓 gTTS 仍被繫結，避免 basedpyright 報「可能未繫結」


def _make_silence_wav(duration_sec: float = 0.5) -> bytes:
    """產生短暫靜音 WAV（用於測試）"""
    sample_rate = 16000
    n_samples = int(sample_rate * duration_sec)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for _ in range(n_samples):
            wav.writeframes(struct.pack("<h", 0))
    return buf.getvalue()


def _make_beep_wav(freq: int = 440, duration_sec: float = 0.3) -> bytes:
    """產生簡單提示音 WAV"""
    sample_rate = 16000
    n_samples = int(sample_rate * duration_sec)
    import math
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for i in range(n_samples):
            t = i / sample_rate
            v = int(3000 * math.sin(2 * math.pi * freq * t))
            v = max(-32768, min(32767, v))
            wav.writeframes(struct.pack("<h", v))
    return buf.getvalue()


def generate_tts(text: str = "測試成功") -> tuple[bytes, str]:
    """產生 TTS 音檔。優先使用 gTTS (MP3)，否則回傳 WAV 提示音。"""
    if HAS_GTTS and gTTS is not None:
        try:
            tts = gTTS(text=text, lang="zh-tw")
            buf = io.BytesIO()
            tts.write_to_fp(buf)
            return buf.getvalue(), "audio/mpeg"
        except Exception:
            pass
    return _make_beep_wav(), "audio/wav"


# 快取最新 TTS，供 /audio/latest 使用
_latest_audio: bytes | None = None
_latest_audio_content_type = "audio/wav"


def set_latest_audio(data: bytes, content_type: str = "audio/wav") -> None:
    global _latest_audio, _latest_audio_content_type
    _latest_audio = data
    _latest_audio_content_type = content_type


def get_latest_audio() -> tuple[bytes, str]:
    global _latest_audio, _latest_audio_content_type
    if _latest_audio is not None:
        return _latest_audio, _latest_audio_content_type
    # 預設回傳提示音
    wav = _make_beep_wav(duration_sec=0.5)
    return wav, "audio/wav"
