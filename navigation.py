"""
連續導航：start_navigation_to_home、stop_navigation、tick_navigation。
支援 next-step 推進、偏航重規劃、到點判定。
"""

import math
import time
from typing import Callable, Optional

import config
from directions_client import get_route
from navigation_state import NavState, get_nav_session


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """兩點經緯度之間的距離（公尺）。"""
    R = 6371000  # 地球半徑（公尺）
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def start_navigation_to_home(
    tts_enqueue_fn: Callable[[str], bool],
    get_last_gps_fn: Callable[[float], Optional[dict]],
    max_age_sec: Optional[float] = None,
) -> bool:
    """
    啟動導航到家。若有有效 GPS 則算路並進入 NAVIGATING，回傳 True；否則 TTS 錯誤並回傳 False。
    """
    session = get_nav_session()
    age = max_age_sec if max_age_sec is not None else getattr(config, "LAST_GPS_MAX_AGE_SEC", 60)
    gps = get_last_gps_fn(age)
    if not gps:
        tts_enqueue_fn("目前無法取得位置，請稍後再試。")
        session.set_last_tts("目前無法取得位置，請稍後再試。")
        return False
    origin_lat = gps["lat"]
    origin_lng = gps["lng"]
    home_lat = getattr(config, "HOME_LAT", 25.0)
    home_lng = getattr(config, "HOME_LNG", 121.5)
    api_key = getattr(config, "GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        tts_enqueue_fn("尚未設定地圖金鑰，無法導航。")
        session.set_last_tts("尚未設定地圖金鑰，無法導航。")
        return False
    summary, steps_list = get_route(origin_lat, origin_lng, home_lat, home_lng, api_key=api_key)
    if not steps_list:
        tts_enqueue_fn("無法規劃回家路線。")
        session.set_last_tts("無法規劃回家路線。")
        return False
    dist_to_home = _haversine_m(origin_lat, origin_lng, home_lat, home_lng)
    session.set_steps(steps_list, dist_to_home=dist_to_home)
    session.set_state(NavState.NAVIGATING)
    session.mark_reroute()
    first_instruction, first_dist_m = steps_list[0]
    dist_str = f"{int(first_dist_m)} 公尺" if first_dist_m else ""
    if len(steps_list) >= 2:
        second_instruction = steps_list[1][0]
        text = f"開始導航回家，距離約 {dist_str}。請{first_instruction}，接著{second_instruction}。"
    else:
        text = f"開始導航回家，距離約 {dist_str}。請{first_instruction}。"
    tts_enqueue_fn(text)
    session.set_last_tts(text)
    return True


def stop_navigation(tts_enqueue_fn: Callable[[str], bool]) -> None:
    """停止導航，回到 IDLE。"""
    session = get_nav_session()
    session.set_state(NavState.IDLE)
    session.clear_route()
    text = "導航已停止。"
    tts_enqueue_fn(text)
    session.set_last_tts(text)


def tick_navigation(
    tts_enqueue_fn: Callable[[str], bool],
    get_last_gps_fn: Callable[[float], Optional[dict]],
    max_age_sec: float = 60,
) -> None:
    """
    導航 tick：在背景週期呼叫。處理 step 推進、到點判定、偏航重規劃。
    """
    session = get_nav_session()
    state = session.get_state()
    if state not in (NavState.NAVIGATING, NavState.BLINDPATH_NAV, NavState.REROUTING):
        return
    gps = get_last_gps_fn(max_age_sec)
    if not gps:
        return
    lat = gps["lat"]
    lng = gps["lng"]
    home_lat = getattr(config, "HOME_LAT", 25.0)
    home_lng = getattr(config, "HOME_LNG", 121.5)
    arrival_radius = getattr(config, "NAV_ARRIVAL_RADIUS_M", 25.0)
    reroute_min_sec = getattr(config, "NAV_REROUTE_MIN_SEC", 30.0)
    dist_to_home = _haversine_m(lat, lng, home_lat, home_lng)
    if dist_to_home <= arrival_radius:
        session.set_state(NavState.ARRIVED)
        session.clear_route()
        text = "您已到達目的地，導航結束。"
        tts_enqueue_fn(text)
        session.set_last_tts(text)
        return
    next_step = session.get_next_step()
    if not next_step:
        return
    instruction, dist_m = next_step
    step_start = session.get_step_start_dist()
    # 若我們已朝目的地前進超過當前 step 的距離，推進到下一步
    if step_start is not None and dist_m > 0:
        decrease = step_start - dist_to_home
        # 直線距離縮短量作為路徑前進的近似；閾值：至少 8m 或 step 長度的 40%，上限 25m
        threshold = max(8, min(dist_m * 0.4, 25))
        if decrease >= threshold:
            if session.advance_step(dist_to_home=dist_to_home):
                new_step = session.get_next_step()
                if new_step:
                    ni, nm = new_step
                    ds = f"{int(nm)} 公尺" if nm else ""
                    text = f"請{ni}，距離約 {ds}。"
                    tts_enqueue_fn(text)
                    session.set_last_tts(text)
            return
    # 若尚未有 step_start，設為當前 dist_to_home
    if step_start is None:
        session.set_step_start_dist(dist_to_home)
    # 重規劃節流：僅在可重規劃時考慮（此處簡化，不實作偏航偵測，由外部依需要觸發）
    if state == NavState.REROUTING and session.can_reroute(reroute_min_sec):
        session.set_state(NavState.NAVIGATING)
