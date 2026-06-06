"""
音訊服務：統一管理 TTS 佇列、語音節流與優先序。
從 main.py 抽離，降低耦合。
"""

from __future__ import annotations

import time
import threading
from typing import Optional

from tts_queue import enqueue as _tts_enqueue, get_latest_path as _tts_latest_path


class AudioService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_tts_text = ""
        self._last_tts_ts = 0.0
        self._min_interval_sec = 0.8

    def enqueue(self, text: str, priority: bool = False) -> bool:
        if not text or not text.strip():
            return False
        now = time.time()
        with self._lock:
            if not priority and text == self._last_tts_text and (now - self._last_tts_ts) < self._min_interval_sec:
                return False
            ok = _tts_enqueue(text)
            if ok:
                self._last_tts_text = text
                self._last_tts_ts = now
            return ok

    def get_latest_path(self) -> Optional[str]:
        return _tts_latest_path()
