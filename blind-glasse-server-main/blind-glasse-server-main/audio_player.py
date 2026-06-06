"""
語音播放介面（上游工作流適配層）

上游導航用 workflow 會直接呼叫 `play_voice_text(...)`，
我們在這裡把它轉成目前專案的 `tts_queue.enqueue(...)`（edge-tts -> audio/latest.mp3）。
"""

from __future__ import annotations

import time
from typing import Any

import config
from tts_queue import enqueue as tts_enqueue


_last_text: str = ""
_last_ts: float = 0.0


def _throttle_sec() -> float:
    # 讓上游語音節流與你現有 TTS 佇列配合；此處提供保守的預防性節流
    return float(getattr(config, "AUDIO_PLAYER_THROTTLE_SEC", 0.7))


def initialize_audio_system() -> None:
    """上游可能會呼叫；在本專案中不需要額外初始化。"""
    return


def play_voice_text(text: str, *args: Any, **kwargs: Any) -> bool:
    """
    上游工作流通用語音入口。

    - text 為空直接跳過
    - 同一句字在短時間內重複則節流（避免隊列積壓）
    """
    global _last_text, _last_ts

    if not text:
        return False

    text = str(text).strip()
    if not text:
        return False

    now = time.time()
    if text == _last_text and (now - _last_ts) < _throttle_sec():
        return False

    ok = bool(tts_enqueue(text))
    if ok:
        _last_text = text
        _last_ts = now
    return ok


def play_audio_on_esp32(*args: Any, **kwargs: Any) -> bool:
    """
    兼容上游/舊碼可能的介面名稱。
    本專案目前由 edge-tts 產出 `audio/latest.mp3` 給 ESP32 拉取播放，
    因此這裡等同於 play_voice_text。
    """
    if args:
        return play_voice_text(args[0])
    return False

