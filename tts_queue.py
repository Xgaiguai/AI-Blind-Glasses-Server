"""
edge-tts 語音佇列：依序將文字轉成語音並寫入固定檔案，供 GET /audio/latest 使用。
"""

import asyncio
import os
import queue
import threading
from pathlib import Path
from typing import Optional

import config

try:
    import edge_tts  # type: ignore[import-untyped]
    _HAS_EDGE_TTS = True
except ImportError:
    _HAS_EDGE_TTS = False

VOICE = getattr(config, "EDGE_TTS_VOICE", "zh-TW-HsiaoChenNeural")
OUTPUT_PATH = getattr(config, "AUDIO_LATEST_PATH", "audio/latest.mp3")
MAX_SIZE = getattr(config, "TTS_QUEUE_MAX_SIZE", 10)

_task_queue: queue.Queue = queue.Queue(maxsize=MAX_SIZE)
_worker_started = False
_lock = threading.Lock()


def _worker() -> None:
    Path(OUTPUT_PATH).parent.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            text = _task_queue.get()
            if text is None:
                break
            if not _HAS_EDGE_TTS:
                continue
            communicate = edge_tts.Communicate(text, VOICE)
            asyncio.run(communicate.save(OUTPUT_PATH))
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
    try:
        _task_queue.put_nowait(text)
        return True
    except queue.Full:
        return False


def get_latest_path() -> str:
    return OUTPUT_PATH
