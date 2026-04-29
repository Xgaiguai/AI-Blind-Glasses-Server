"""
意圖路由：依 ASR 辨識意圖 dispatch 到對應動作。
"""

from typing import Callable, Dict, Optional, Any

from asr_intent import (
    INTENT_ITEM_SEARCH,
    INTENT_ITEM_FOUND,
    INTENT_NAV_HOME,
    INTENT_OTHER,
    INTENT_SCENE_DESC,
    INTENT_STOP_NAV,
    INTENT_TRAFFIC_LIGHT,
    INTENT_DISTRESS,
    get_voice_intent,
)


def route_intent(
    intent_payload: Dict[str, Optional[str]],
    tts_enqueue_fn: Callable[[str], bool],
    get_last_gps_fn: Callable[[float], Optional[dict]],
    request_scene_desc_fn: Callable[[], None],
    request_traffic_light_fn: Callable[[], None],
    start_nav_fn: Callable[[], None],
    stop_nav_fn: Callable[[], None],
    start_item_search_fn: Callable[[str], None],
    stop_item_search_fn: Callable[[], None],
    on_distress_fn: Optional[Callable[[], None]] = None,
    max_gps_age_sec: float = 60,
) -> None:
    """
    依意圖執行對應動作。各 fn 為實際執行的回呼。
    """
    intent = intent_payload.get("intent") or INTENT_OTHER
    target = (intent_payload.get("target") or "").strip()

    if intent == INTENT_NAV_HOME:
        start_nav_fn()
    elif intent == INTENT_STOP_NAV:
        stop_nav_fn()
    elif intent == INTENT_SCENE_DESC:
        request_scene_desc_fn()
    elif intent == INTENT_ITEM_SEARCH:
        # 若模型沒有抽到目標名，仍先開啟 item_search，worker 內會用 fallback 提示。
        start_item_search_fn(target)
    elif intent == INTENT_ITEM_FOUND:
        stop_item_search_fn()
    elif intent == INTENT_TRAFFIC_LIGHT:
        request_traffic_light_fn()
    elif intent == INTENT_DISTRESS:
        if on_distress_fn:
            on_distress_fn()
        else:
            tts_enqueue_fn("已收到，正在為您聯絡家屬。")
    else:
        tts_enqueue_fn("已收到語音指令，正在處理。")


def handle_asr_and_route(
    audio_wav_bytes: bytes,
    tts_enqueue_fn: Callable[[str], bool],
    get_last_gps_fn: Callable[[float], Optional[dict]],
    request_scene_desc_fn: Callable[[], None],
    request_traffic_light_fn: Callable[[], None],
    start_nav_fn: Callable[[], None],
    stop_nav_fn: Callable[[], None],
    start_item_search_fn: Callable[[str], None],
    stop_item_search_fn: Callable[[], None],
    on_distress_fn: Optional[Callable[[], None]] = None,
    max_gps_age_sec: float = 60,
) -> str:
    """
    從 WAV 辨識意圖並路由。在 run_in_executor 內呼叫。
    """
    intent_payload = get_voice_intent(audio_wav_bytes)
    intent = intent_payload.get("intent") or INTENT_OTHER
    target = (intent_payload.get("target") or "").strip()

    route_intent(
        intent_payload,
        tts_enqueue_fn,
        get_last_gps_fn,
        request_scene_desc_fn,
        request_traffic_light_fn,
        start_nav_fn,
        stop_nav_fn,
        start_item_search_fn,
        stop_item_search_fn,
        on_distress_fn=on_distress_fn,
        max_gps_age_sec=max_gps_age_sec,
    )
    if intent == INTENT_ITEM_SEARCH:
        return f"{intent}:{target or ''}".rstrip(":")
    return str(intent)
