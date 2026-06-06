"""
Google Directions API：依起點、終點取得步行路線與 steps。
"""

import re
from typing import List, Optional, Tuple

import requests  # type: ignore[import-untyped]

import config

DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"


def get_route(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    api_key: Optional[str] = None,
    mode: str = "walking",
) -> Tuple[Optional[str], List[Tuple[str, float]]]:
    """
    取得步行路線。回傳 (summary_text 或 None, steps_list)。
    steps_list 每項為 (instruction 簡短中文, distance_m)。
    """
    key = api_key or getattr(config, "GOOGLE_MAPS_API_KEY", "")
    if not key:
        return None, []

    origin = f"{origin_lat},{origin_lng}"
    destination = f"{dest_lat},{dest_lng}"
    params = {
        "origin": origin,
        "destination": destination,
        "mode": mode,
        "key": key,
        "language": "zh-TW",
    }

    try:
        r = requests.get(DIRECTIONS_URL, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError) as e:
        print(f"[Directions] Error: {e}")
        return None, []

    if data.get("status") != "OK" or not data.get("routes"):
        return None, []

    # 節流：重規劃呼叫由導航模組控制，此處僅回傳資料
    route = data["routes"][0]
    summary = route.get("summary", "")
    legs = route.get("legs", [])
    if not legs:
        return summary or None, []

    steps_list: List[Tuple[str, float]] = []
    for step in legs[0].get("steps", []):
        dist = step.get("distance", {}).get("value", 0)
        dist_m = float(dist) if dist else 0.0
        raw = step.get("html_instructions", "") or step.get("maneuver", "") or "直行"
        instruction = _html_to_short_instruction(raw)
        steps_list.append((instruction, dist_m))

    return summary or None, steps_list


def _html_to_short_instruction(html: str) -> str:
    """簡化 HTML 指示為一句短中文，適合 TTS。"""
    text = re.sub(r"<[^>]+>", "", html)
    text = text.strip()
    if not text:
        return "直行"
    if "Turn right" in text or "右轉" in text:
        return "右轉"
    if "Turn left" in text or "左轉" in text:
        return "左轉"
    if "Head" in text or "直行" in text:
        return "直行"
    if len(text) > 30:
        return text[:30] + "…"
    return text or "直行"
