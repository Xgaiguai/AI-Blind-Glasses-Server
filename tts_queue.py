"""
edge-tts 語音佇列：依序將文字轉成語音並寫入版本化檔案，供 GET /audio/latest 使用。
使用序號管理避免讀寫競爭：先寫入 latest_<seq>.mp3，再原子更新指標。
"""

import asyncio
import os
import queue
import threading
import time
from pathlib import Path
from typing import Optional

import config

try:
    import edge_tts  # type: ignore[import-untyped]
    _HAS_EDGE_TTS = True
except ImportError:
    _HAS_EDGE_TTS = False

VOICE = getattr(config, "EDGE_TTS_VOICE", "zh-TW-HsiaoChenNeural")
OUTPUT_DIR = str(Path(getattr(config, "AUDIO_LATEST_PATH", "audio/latest.mp3")).parent)
MAX_SIZE = getattr(config, "TTS_QUEUE_MAX_SIZE", 10)
MAX_KEEP_FILES = 5

_task_queue: queue.Queue = queue.Queue(maxsize=MAX_SIZE)
_worker_started = False
_lock = threading.Lock()

_last_enqueued_text: str = ""
_last_enqueued_ts: float = 0.0

_seq_lock = threading.Lock()
_current_seq: int = 0
_current_path: Optional[str] = None


def _seq_path(seq: int) -> str:
    return os.path.join(OUTPUT_DIR, f"latest_{seq:06d}.mp3")


def _cleanup_old(keep: int = MAX_KEEP_FILES) -> None:
    try:
        files = sorted(Path(OUTPUT_DIR).glob("latest_*.mp3"))
        for f in files[:-keep]:
            try:
                f.unlink()
            except OSError:
                pass
    except Exception:
        pass


def _worker() -> None:
    global _current_seq, _current_path
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    legacy_path = os.path.join(OUTPUT_DIR, "latest.mp3")

    while True:
        try:
            text = _task_queue.get()
            if text is None:
                break
            if not _HAS_EDGE_TTS:
                continue

            with _seq_lock:
                _current_seq += 1
                seq = _current_seq

            out_path = _seq_path(seq)
            communicate = edge_tts.Communicate(text, VOICE)
            asyncio.run(communicate.save(out_path))

            with _seq_lock:
                _current_path = out_path

            try:
                if os.path.exists(legacy_path) or not os.path.islink(legacy_path):
                    if os.path.exists(legacy_path):
                        os.remove(legacy_path)
                import shutil
                shutil.copy2(out_path, legacy_path)
            except Exception:
                pass

            _cleanup_old()

        except Exception as e:
            print(f"[TTS] Error: {e}")
        finally:
            try:
                _task_queue.task_done()
            except ValueError:
                pass


def start_worker() -> None:
    global _worker_started
    with _lock:
        if _worker_started:
            return
        _worker_started = True
    t = threading.Thread(target=_worker, daemon=True)
    t.start()


def enqueue(text: str) -> bool:
    """將文字加入 TTS 佇列，回傳是否成功加入。"""
    start_worker()
    global _last_enqueued_text, _last_enqueued_ts
    try:
        text = str(text).strip()
        if not text:
            return False

        throttle_sec = float(getattr(config, "TTS_ENQUEUE_DEDUP_THROTTLE_SEC", 0.7))
        now = time.time()
        if text == _last_enqueued_text and (now - _last_enqueued_ts) < throttle_sec:
            return False

        _task_queue.put_nowait(text)
        _last_enqueued_text = text
        _last_enqueued_ts = now
        return True
    except queue.Full:
        return False


def get_latest_path() -> Optional[str]:
    """回傳最新版本化音檔路徑（或 legacy latest.mp3）。"""
    with _seq_lock:
        if _current_path and os.path.exists(_current_path):
            return _current_path
    legacy = os.path.join(OUTPUT_DIR, "latest.mp3")
    if os.path.exists(legacy):
        return legacy
    return None


def get_current_seq() -> int:
    with _seq_lock:
        return _current_seq
