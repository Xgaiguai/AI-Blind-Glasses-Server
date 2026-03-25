"""
意圖路由：依 ASR 辨識意圖 dispatch 到對應動作。
"""

from typing import Callable, Optional

from asr_intent import (
    INTENT_ITEM_SEARCH,
    INTENT_NAV_HOME,
    INTENT_OTHER,
    INTENT_SCENE_DESC,
    INTENT_STOP_NAV,
    INTENT_TRAFFIC_LIGHT,
    get_voice_intent,
)


def route_intent(
    intent: str,
    tts_enqueue_fn: Callable[[str], bool],
    get_last_gps_fn: Callable[[float], Optional[dict]],
    request_scene_desc_fn: Callable[[], None],
    request_item_search_fn: Callable[[], None],
    request_traffic_light_fn: Callable[[], None],
    start_nav_fn: Callable[[], None],
    stop_nav_fn: Callable[[], None],
    max_gps_age_sec: float = 60,
) -> None:
    """
    依意圖執行對應動作。各 fn 為實際執行的回呼。
    """
    if intent == INTENT_NAV_HOME:
        start_nav_fn()
    elif intent == INTENT_STOP_NAV:
        stop_nav_fn()
    elif intent == INTENT_SCENE_DESC:
        request_scene_desc_fn()
    elif intent == INTENT_ITEM_SEARCH:
        request_item_search_fn()
    elif intent == INTENT_TRAFFIC_LIGHT:
        request_traffic_light_fn()
    else:
        tts_enqueue_fn("已收到語音指令，正在處理。")


def handle_asr_and_route(
    audio_wav_bytes: bytes,
    tts_enqueue_fn: Callable[[str], bool],
    get_last_gps_fn: Callable[[float], Optional[dict]],
    request_scene_desc_fn: Callable[[], None],
    request_item_search_fn: Callable[[], None],
    request_traffic_light_fn: Callable[[], None],
    start_nav_fn: Callable[[], None],
    stop_nav_fn: Callable[[], None],
    max_gps_age_sec: float = 60,
) -> str:
    """
    從 WAV 辨識意圖並路由。在 run_in_executor 內呼叫。
    """
    intent = get_voice_intent(audio_wav_bytes)
    route_intent(
        intent,
        tts_enqueue_fn,
        get_last_gps_fn,
        request_scene_desc_fn,
        request_item_search_fn,
        request_traffic_light_fn,
        start_nav_fn,
        stop_nav_fn,
        max_gps_age_sec,
    )
    return intent
