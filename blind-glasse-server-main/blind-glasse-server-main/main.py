"""
智慧導盲眼鏡 - FastAPI 伺服器
通訊與即時影像、UDP 發現、YOLO 避障、Gemini / TTS、導航狀態機、監控介面。
"""

import asyncio
import base64
import hashlib
import hmac
import logging
import os
import sys
import warnings
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

import cv2  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]
import requests  # type: ignore[import-untyped]
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect  # type: ignore[import-untyped]
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse  # type: ignore[import-untyped]

import config

# Ultralytics 有時用 print / 直寫 stderr 打出「GitHub assets check failure」，logging.Filter 吃不到。
_stderr_github_filter_installed = False


class _StderrGitHubNoiseFilter:
    """依行緩衝 stderr，丟棄 Ultralytics 對 GitHub releases 的資產檢查洗版訊息。"""

    def __init__(self, underlying):
        object.__setattr__(self, "_underlying", underlying)
        object.__setattr__(self, "_buf", "")

    def write(self, s) -> int:
        if isinstance(s, bytes):
            enc = getattr(self._underlying, "encoding", None) or "utf-8"
            s = s.decode(enc, errors="replace")
        elif not isinstance(s, str):
            s = str(s)
        self._buf += s
        n = len(s)
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            line += "\n"
            if _is_ultralytics_github_assets_stderr_noise(line):
                continue
            self._underlying.write(line)
        return n

    def flush(self) -> None:
        if self._buf:
            if not _is_ultralytics_github_assets_stderr_noise(self._buf):
                self._underlying.write(self._buf)
            self._buf = ""
        self._underlying.flush()

    def __getattr__(self, name):
        return getattr(self._underlying, name)


def _is_ultralytics_github_assets_stderr_noise(line: str) -> bool:
    if "GitHub assets check failure" in line:
        return True
    if "api.github.com/repos/ultralytics/assets" in line:
        low = line.lower()
        if "429" in line or "403" in line or "rate limit" in low:
            return True
    return False


class _DropUltralyticsGitHubRateLimitLogFilter(logging.Filter):
    """壓掉 Ultralytics 對 GitHub API 做 assets 檢查時的 403 rate limit WARNING（不影響推論，只少洗版）。"""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        if "GitHub assets check failure" in msg:
            return False
        return True


def _suppress_ultralytics_github_log_noise() -> None:
    global _stderr_github_filter_installed
    if not _stderr_github_filter_installed:
        sys.stderr = _StderrGitHubNoiseFilter(sys.__stderr__)
        _stderr_github_filter_installed = True
    filt = _DropUltralyticsGitHubRateLimitLogFilter()
    logging.getLogger().addFilter(filt)
    for name in (
        "ultralytics",
        "ultralytics.hub",
        "ultralytics.nn",
        "ultralytics.utils",
        "ultralytics.models",
    ):
        lg = logging.getLogger(name)
        lg.addFilter(filt)
        lg.setLevel(logging.ERROR)
    warnings.filterwarnings("ignore", message=r".*GitHub assets check failure.*")


_suppress_ultralytics_github_log_noise()

from asr_intent import get_last_transcript
from gemini_client import analyze_scene
from line_gemini_chat import family_line_reply
from line_bot_router import router as line_bot_router
from imu_gps_fusion import get_fusion
from intent_router import handle_asr_and_route
from monitor_api import create_monitor_router
from navigation import start_navigation_to_home, stop_navigation, tick_navigation
from navigation_state import NavState, get_nav_session
from stream_manager import stream_manager
from traffic_crossing import get_controller
from udp_discovery import _get_local_ip, start_udp_listener_thread
from yolo_detector import get_detector
from tts_queue import enqueue as tts_enqueue, get_latest_path as tts_latest_path, get_current_seq as tts_current_seq
from vision_controller import VisionController
from event_engine import EventEngine
from line_notifier import LineNotifier
from server_health import ServerHealth
from item_search_worker import (
    start_item_search as start_item_search_worker,
    stop_item_search as stop_item_search_worker,
    get_snapshot as get_item_search_snapshot,
)
import ws_broadcaster


def _api_error(error: str, status_code: int, detail: Optional[str] = None):
    payload: Dict[str, object] = {"ok": False, "error": error}
    if detail:
        payload["detail"] = detail
    return JSONResponse(payload, status_code=status_code)


def _log_exception(tag: str, exc: Exception) -> None:
    print(f"[ERROR][{tag}] {exc}")


def _validate_startup_config() -> None:
    warnings: List[str] = []
    errors: List[str] = []

    if not getattr(config, "DEVICE_API_TOKEN", "").strip():
        msg = "DEVICE_API_TOKEN 未設定，裝置 API 將不會啟用 token 驗證。"
        if getattr(config, "REQUIRE_DEVICE_API_TOKEN", False):
            errors.append(msg)
        else:
            warnings.append(msg)

    if getattr(config, "HOME_LAT", 25.0) == 25.0 and getattr(config, "HOME_LNG", 121.5) == 121.5:
        warnings.append("HOME_LAT/HOME_LNG 仍為預設值，導航到家可能指向錯誤地點。")

    if getattr(config, "LINE_NOTIFY_ENABLE", False):
        if not getattr(config, "LINE_CHANNEL_ACCESS_TOKEN", "").strip():
            warnings.append("LINE_NOTIFY_ENABLE=1 但 LINE_CHANNEL_ACCESS_TOKEN 未設定。")
        if not getattr(config, "LINE_TARGET_IDS", "").strip():
            warnings.append("LINE_NOTIFY_ENABLE=1 但 LINE_TARGET_IDS 未設定。")

    for w in warnings:
        print(f"[WARN][config] {w}")
    if errors:
        raise RuntimeError(" ; ".join(errors))

# 背景 YOLO 更新之避障文字（thread-safe）
_obstacle_lock = threading.Lock()
_latest_obstacle_text: Optional[str] = None

# 最後一筆 GPS（供導航起點用）
_gps_lock = threading.Lock()
_last_gps: Optional[dict] = None  # {"lat", "lng", "ts"} 或含 alt, sat, course

# 監控: 最近語音意圖
_voice_lock = threading.Lock()
_recent_voice_intents: List[Dict[str, str]] = []

_yolo_interval_sec = config.YOLO_INTERVAL_SEC
_nav_interval_sec = config.NAV_INTERVAL_SEC
_crossing_interval_sec = config.CROSSING_INTERVAL_SEC
_yolo_stop = threading.Event()
_nav_stop = threading.Event()
_vision_stop = threading.Event()

# 視覺疊字 controller：輸出 annotated frame 給監控/前端
_vision_controller = VisionController()

# 視覺驅動模式：
# - 預設為關閉（仍使用既有 `_nav_worker` 驅動導航/紅綠燈語音）
# - 需要時可設定環境變數 `ENABLE_VISION_DRIVE=1` 讓 `_vision_worker` 代替 `_nav_worker`
_VISION_DRIVE_ENABLED = os.environ.get("ENABLE_VISION_DRIVE", "0") == "1"

# 家屬通知與事件引擎
_event_engine = EventEngine()
_line_notifier = LineNotifier()
_server_health = ServerHealth()
_asr_executor = ThreadPoolExecutor(
    max_workers=max(1, int(getattr(config, "ASR_EXECUTOR_MAX_WORKERS", 2))),
    thread_name_prefix="asr",
)
_gemini_executor = ThreadPoolExecutor(
    max_workers=max(1, int(getattr(config, "GEMINI_EXECUTOR_MAX_WORKERS", 2))),
    thread_name_prefix="gemini",
)
_line_ai_executor = ThreadPoolExecutor(
    max_workers=max(1, int(getattr(config, "LINE_AI_EXECUTOR_MAX_WORKERS", 2))),
    thread_name_prefix="line-ai",
)
_viewer_ws_interval_sec = max(0.01, float(getattr(config, "VIEWER_WS_INTERVAL_SEC", 0.05)))
_asr_default_async = bool(getattr(config, "ASR_DEFAULT_ASYNC", True))
# 同時進行中的 ASR / Gemini 任務數上限（threading.Semaphore，避免無限制堆疊背景任務）
_asr_job_sem = threading.Semaphore(max(1, int(getattr(config, "API_ASR_MAX_JOBS", 8))))
_gemini_job_sem = threading.Semaphore(max(1, int(getattr(config, "API_GEMINI_MAX_JOBS", 3))))
_asr_wait_queue_max = max(0, int(getattr(config, "ASR_WAIT_QUEUE_MAX", 4)))
_asr_wait_lock = threading.Lock()
_asr_wait_queue: deque[bytes] = deque()


# 僅在這些路徑從 client IP 推斷 ESP32（避免 LINE Webhook、瀏覽器把 LINE/本機 IP 當成相機）
# 不含 /health：手機瀏覽器常會打 /health 測試，會誤把使用者 IP 當成 ESP32 而狂拉 :81/stream
_ESP32_IP_FROM_REQUEST_PATHS = frozenset(
    {
        "/api/gemini",
        "/api/asr",
        "/api/imu",
        "/api/gps",
        "/api/frame",
        "/audio/latest",
    }
)


def _should_record_esp32_ip_from_request(request: Request) -> bool:
    return request.url.path in _ESP32_IP_FROM_REQUEST_PATHS


_MAX_DEVICE_STREAM_URL_LEN = 512


def _safe_device_stream_url(raw: str) -> Optional[str]:
    """驗證韌體回報的 MJPEG URL，避免 SSRF／標頭注入。"""
    u = (raw or "").strip()
    if not u or len(u) > _MAX_DEVICE_STREAM_URL_LEN:
        return None
    low = u.lower()
    if not (low.startswith("http://") or low.startswith("https://")):
        return None
    if any(c in u for c in ("\r", "\n", "\x00")):
        return None
    return u


def _record_esp32_ip_from_request(request: Request) -> None:
    """從請求來源 IP 記錄 ESP32，並啟動串流拉取。"""
    client = request.client
    if client:
        host = client.host
        stream_manager.set_esp32_ip(host)
        # 診斷：終端機若從未出現此行，代表眼鏡沒打到這台伺服器（或 IP 被記成 127.0.0.1）
        if host not in ("127.0.0.1", "::1") and request.url.path in (
            "/api/imu",
            "/api/gps",
            "/api/asr",
        ):
            print(f"[ESP32] 已記錄裝置 {host} ← {request.method} {request.url.path}，開始嘗試拉 MJPEG")


def _push_voice_intent(text: str) -> None:
    with _voice_lock:
        _recent_voice_intents.append({"ts": str(time.time()), "text": text})
        if len(_recent_voice_intents) > 20:
            del _recent_voice_intents[:-20]


def _build_asr_runner(audio_body: bytes):
    """回傳可在 executor 內執行的同步 callable（依 bytes 綁定）。"""

    def _run() -> str:
        return handle_asr_and_route(
            audio_body,
            tts_enqueue_fn=tts_enqueue,
            get_last_gps_fn=_get_last_gps,
            request_scene_desc_fn=lambda: _request_scene_desc("general"),
            request_traffic_light_fn=lambda: get_controller().start(),
            start_nav_fn=lambda: start_navigation_to_home(tts_enqueue, _get_last_gps, config.LAST_GPS_MAX_AGE_SEC),
            stop_nav_fn=lambda: stop_navigation(tts_enqueue),
            start_item_search_fn=lambda target: _start_item_search(target or ""),
            stop_item_search_fn=_stop_item_search,
            on_distress_fn=_handle_voice_distress,
            max_gps_age_sec=config.LAST_GPS_MAX_AGE_SEC,
        )

    return _run


async def _asr_schedule_next_from_queue() -> None:
    """非同步 ASR 槽位釋放後，自等候佇列啟動下一筆。"""
    body: Optional[bytes] = None
    with _asr_wait_lock:
        if not _asr_wait_queue:
            return
        body = _asr_wait_queue.popleft()
    if body is None:
        return
    if not _asr_job_sem.acquire(blocking=False):
        with _asr_wait_lock:
            _asr_wait_queue.appendleft(body)
        return
    loop = asyncio.get_running_loop()
    rid = f"asr-q-{int(time.time() * 1000)}"
    _server_health.latency.begin(rid, "arrive")
    _server_health.latency.mark(rid, "dequeued")
    audio_chunk = body

    async def _bg_queued() -> None:
        runner = _build_asr_runner(audio_chunk)
        try:
            intent = await loop.run_in_executor(_asr_executor, runner)
            _push_voice_intent(intent)
            _server_health.latency.finish(rid, "bg_done")
        except Exception as e:
            _server_health.set_error(f"asr_bg:{e}")
        finally:
            _asr_job_sem.release()
            await _asr_schedule_next_from_queue()

    asyncio.create_task(_bg_queued())


def _get_latest_frame_bytes() -> Optional[bytes]:
    frame_b, _ = stream_manager.get_latest_frame()
    if not frame_b or not stream_manager.has_recent_frame():
        return None
    return frame_b


def _get_latest_viewer_frame_bytes() -> Optional[bytes]:
    """給前端顯示的影像：優先 annotated，否則 fallback raw（VIEWER_PREFER_RAW=1 時只推原圖以降低延遲）。"""
    if bool(getattr(config, "VIEWER_PREFER_RAW", False)):
        return _get_latest_frame_bytes()
    try:
        annotated = _vision_controller.get_latest_annotated_frame_bytes()
        if annotated:
            return annotated
    except Exception as e:
        _log_exception("viewer_frame", e)
    return _get_latest_frame_bytes()


def _is_recursive_esp32_stream_proxy(upstream: str, request_host: str) -> bool:
    """若上游指向本機對外網址或本機 HTTP 埠的 /stream，會形成無窮迴圈。"""
    from urllib.parse import urlparse

    try:
        p = urlparse(upstream.strip())
        path_l = (p.path or "").lower()
        if "/stream" not in path_l:
            return False
        h = (p.hostname or "").lower()
        rqh = (request_host.split(":")[0] if request_host else "").lower()
        port = p.port
        if p.scheme == "https" and port is None:
            port = 443
        elif p.scheme == "http" and port is None:
            port = 80
        http_app = int(getattr(config, "HTTP_PORT", 5000))
        if rqh and h == rqh and port in (80, 443):
            return True
        if h in {"127.0.0.1", "localhost", "::1"} and port == http_app:
            return True
        return False
    except Exception:
        return False


_STREAM_CACHE_MJPEG_INTERVAL_SEC = max(
    0.01, float(getattr(config, "MJPEG_PUBLIC_CACHE_INTERVAL_SEC", 0.05))
)


def _request_scene_desc(mode: str = "general") -> None:
    frame_b = _get_latest_frame_bytes()
    if not frame_b:
        tts_enqueue("目前沒有可用畫面。")
        return
    text = analyze_scene(frame_b, extra_prompt=f"（模式：{mode}）")
    tts_enqueue(text)


def _notify_family_text(text: str) -> None:
    try:
        _line_notifier.push_text(text)
    except Exception as e:
        _log_exception("line_notify_text", e)


def _notify_family_location() -> None:
    gps = _event_engine.get_snapshot().get("last_gps") or {}
    lat = gps.get("lat")
    lng = gps.get("lng")
    if lat is None or lng is None:
        return
    try:
        _line_notifier.push_location(
            title="眼鏡目前位置",
            address=gps.get("map_url") or "Google Maps",
            lat=float(lat),
            lng=float(lng),
        )
    except Exception as e:
        _log_exception("line_notify_location", e)


def _build_family_status_text() -> str:
    snap = _event_engine.get_snapshot()
    gps = snap.get("last_gps") or {}
    fall = snap.get("fall") or {}
    health = _server_health.snapshot()
    return (
        f"伺服器狀態\n"
        f"- Uptime: {health.get('uptime_sec')}s\n"
        f"- IMU age: {health.get('last_imu_age_sec')}\n"
        f"- GPS age: {health.get('last_gps_age_sec')}\n"
        f"- 跌倒警示: {'ALERT' if fall.get('active') else 'normal'}\n"
        f"- GPS: {gps.get('lat')}, {gps.get('lng')}"
    )


def _build_family_location_text() -> str:
    gps = (_event_engine.get_snapshot().get("last_gps") or {})
    lat = gps.get("lat")
    lng = gps.get("lng")
    map_url = gps.get("map_url") or ""
    if lat is None or lng is None:
        return "目前尚未收到 GPS 定位資料。"
    return f"眼鏡目前位置：{lat}, {lng}\n地圖：{map_url}"


def _line_gemini_context() -> str:
    """給 LINE 家屬對話用的純文字摘要。"""
    st = _build_family_status_text()
    loc = _build_family_location_text()
    return f"{st}\n\n{loc}"


def _handle_voice_distress() -> None:
    """眼鏡端語音辨識為求救意圖時：推播家屬並 TTS 安撫。"""
    note = get_last_transcript()
    _event_engine.emergency_event("voice_distress")
    if _event_engine.should_send_line():
        msg = "【語音緊急】使用者透過眼鏡表達需要協助，請儘速聯繫確認安全。"
        if note:
            msg += f"\n（語音轉寫：{note[:120]}{'…' if len(note) > 120 else ''}）"
        _notify_family_text(msg)
        _notify_family_location()
    tts_enqueue("我已嘗試通知您的家屬，請留在相對安全處並保持通訊。")


_item_search_lock = threading.Lock()
_item_search_active = False
_item_search_target: Optional[str] = None


def _start_item_search(target: str) -> None:
    """啟動物品查找（改為背景 worker）。"""
    global _item_search_active, _item_search_target
    with _item_search_lock:
        _item_search_active = True
        _item_search_target = target or ""
    if target and target.strip():
        tts_enqueue(f"好的，我正在找 {target}。")
    else:
        tts_enqueue("好的，我正在找你要的物品。")
    # 由 worker 持續產出引導語音
    start_item_search_worker(target, _get_latest_frame_bytes, tts_enqueue)


def _stop_item_search() -> None:
    """停止物品查找。"""
    global _item_search_active, _item_search_target
    with _item_search_lock:
        _item_search_active = False
        _item_search_target = None
    stop_item_search_worker()
    tts_enqueue("物品查找已結束。")


def _yolo_worker() -> None:
    """背景執行：定期取最新幀跑 YOLO，更新避障文字。"""
    global _latest_obstacle_text
    det = get_detector()
    while not _yolo_stop.is_set():
        # 物品查找時先把語音與推論資源讓給尋物 worker，避免多模組同時播報干擾
        if _item_search_active:
            time.sleep(0.5)
            continue
        frame_b = _get_latest_frame_bytes()
        had_frame = bool(frame_b)
        if frame_b:
            try:
                arr = np.frombuffer(frame_b, dtype=np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if img is not None:
                    h, w = img.shape[:2]
                    detections = det.run_inference(img)
                    text = det.analyze_for_obstacle(detections, w, h)
                    with _obstacle_lock:
                        _latest_obstacle_text = text
            except Exception:
                print("[WARN][yolo] inference failed once")
        # 有畫面時依 YOLO_INTERVAL 節流；無畫面時短睡，避免空轉又降低「有串流後」的首幀延遲
        time.sleep(_yolo_interval_sec if had_frame else 0.02)
    _yolo_stop.clear()


def _nav_worker() -> None:
    """背景執行：導航 tick + 紅綠燈流程 tick。"""
    nav_session = get_nav_session()
    crossing = get_controller()
    while not _nav_stop.is_set():
        try:
            # 物品查找時跳過導航/紅綠燈 tick，避免同時 enqueue TTS
            if _item_search_active:
                nav_session.set_state(NavState.ITEM_SEARCH)
                time.sleep(0.5)
                continue
            tick_navigation(tts_enqueue, _get_last_gps, config.LAST_GPS_MAX_AGE_SEC)
            crossing.tick(_get_latest_frame_bytes, tts_enqueue)

            # 將 crossing 狀態同步到導航 session（供監控顯示）
            c_state = crossing.get_state().get("state")
            s = nav_session.get_state()
            if c_state == "wait":
                nav_session.set_state(NavState.WAIT_TRAFFIC_LIGHT)
            elif c_state in ("go", "recheck"):
                nav_session.set_state(NavState.CROSSING)
            elif c_state == "idle" and s in (NavState.WAIT_TRAFFIC_LIGHT, NavState.CROSSING):
                nav_session.set_state(NavState.BLINDPATH_NAV if nav_session.get_steps() else NavState.IDLE)
            elif c_state == "idle" and s in (NavState.NAVIGATING, NavState.REROUTING):
                # 視覺模式名稱對齊：讓監控 UI 看起來像在走盲道導航
                nav_session.set_state(NavState.BLINDPATH_NAV if nav_session.get_steps() else NavState.IDLE)
        except Exception as e:
            _log_exception("nav_worker", e)
        time.sleep(min(_nav_interval_sec, _crossing_interval_sec))
    _nav_stop.clear()


def _vision_worker() -> None:
    """背景執行：將最新 raw frame 做疊字並更新 annotated JPEG。"""
    nav_session = get_nav_session()
    crossing = get_controller()
    while not _vision_stop.is_set():
        try:
            # 視覺模式驅動：用 vision_worker 取代 nav_worker，避免雙重 enqueue TTS
            if _VISION_DRIVE_ENABLED:
                if _item_search_active:
                    nav_session.set_state(NavState.ITEM_SEARCH)
                    time.sleep(0.5)
                else:
                    tick_navigation(tts_enqueue, _get_last_gps, config.LAST_GPS_MAX_AGE_SEC)
                    crossing.tick(_get_latest_frame_bytes, tts_enqueue)

                    # 將 crossing 狀態同步到導航 session（供監控顯示）
                    c_state = crossing.get_state().get("state")
                    s = nav_session.get_state()
                    if c_state == "wait":
                        nav_session.set_state(NavState.WAIT_TRAFFIC_LIGHT)
                    elif c_state in ("go", "recheck"):
                        nav_session.set_state(NavState.CROSSING)
                    elif c_state == "idle" and s in (NavState.WAIT_TRAFFIC_LIGHT, NavState.CROSSING):
                        nav_session.set_state(NavState.BLINDPATH_NAV if nav_session.get_steps() else NavState.IDLE)
                    elif c_state == "idle" and s in (NavState.NAVIGATING, NavState.REROUTING):
                        # 視覺模式名稱對齊：讓監控 UI 看起來像在走盲道導航
                        nav_session.set_state(NavState.BLINDPATH_NAV if nav_session.get_steps() else NavState.IDLE)

            # 更新疊字畫面
            frame_b = _get_latest_frame_bytes()
            if frame_b:
                _vision_controller.tick(frame_b)

        except Exception as e:
            _log_exception("vision_worker", e)

        if _VISION_DRIVE_ENABLED:
            time.sleep(min(_nav_interval_sec, _crossing_interval_sec))
        else:
            time.sleep(0.05)
    _vision_stop.clear()


def _monitor_state() -> Dict[str, object]:
    nav_session = get_nav_session()
    fusion = get_fusion()
    crossing = get_controller()
    with _voice_lock:
        recent_voice = list(_recent_voice_intents[-5:])

    # Vision overlay detector summary. This matches the model used to draw boxes
    # on /monitor, /ws/viewer, and /api/monitor/frame.
    try:
        vision_data: Dict[str, object] = _vision_controller.get_detection_summary()
    except Exception as e:
        _log_exception("monitor_state", e)
        vision_data = {
            "model_loaded": False,
            "model_path": "",
            "configured_paths": [],
            "last_target": None,
            "last_confidence": 0.0,
            "detection_count": 0,
            "top_k": [],
            "last_error": str(e),
        }

    return {
        "mode": nav_session.get_state().value,
        "navigation": nav_session.get_snapshot(),
        "fusion": fusion.get_snapshot(),
        "traffic_light": crossing.get_state(),
        "item_search": get_item_search_snapshot(),
        "vision": vision_data,
        "recent_voice": recent_voice,
        "esp32_ip": stream_manager.get_esp32_ip(),
        "family": _event_engine.get_snapshot(),
        "server_health": _server_health.snapshot(),
    }


def _monitor_events(limit: int) -> List[Dict[str, object]]:
    return get_nav_session().get_recent_events(limit=limit)


class _QuietMonitorFrameAccessLogFilter(logging.Filter):
    """略過監控頁輪詢 /api/monitor/frame 的 204／304，避免洗版 uvicorn access log。"""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        if "/api/monitor/frame" not in msg:
            return True
        if " 204" in msg or " 304" in msg:
            return False
        return True


_monitor_frame_access_filter_installed = False


def _install_quiet_access_logging() -> None:
    global _monitor_frame_access_filter_installed
    if _monitor_frame_access_filter_installed:
        return
    logging.getLogger("uvicorn.access").addFilter(_QuietMonitorFrameAccessLogFilter())
    _monitor_frame_access_filter_installed = True


@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_startup_config()
    _install_quiet_access_logging()
    # 雲端部署：通常 UDP discovery 不通，因此可用 ENABLE_UDP_DISCOVERY / ESP32_STREAM_URL 控制行為
    esp32_stream_url = (getattr(config, "ESP32_STREAM_URL", "") or "").strip()
    enable_udp = bool(getattr(config, "ENABLE_UDP_DISCOVERY", True))

    if enable_udp and not esp32_stream_url:
        start_udp_listener_thread(on_esp32_seen=stream_manager.set_esp32_ip)

    # 若已提供可被雲端存取的串流 URL，就先啟動 MJPEG puller（不依賴 UDP）。
    if esp32_stream_url and not stream_manager.get_esp32_ip():
        stream_manager.set_esp32_ip("esp32-stream-url")

    yolo_thread = threading.Thread(target=_yolo_worker, daemon=True)
    nav_thread = threading.Thread(target=_nav_worker, daemon=True)
    vision_thread = threading.Thread(target=_vision_worker, daemon=True)
    yolo_thread.start()
    if not _VISION_DRIVE_ENABLED:
        nav_thread.start()
    vision_thread.start()
    print(
        "[提示] 陀螺儀三軸／加速度三軸是 HTTP POST /api/imu（六軸），不是 UDP；UDP 只有「找伺服器」(WHO_IS_SERVER)。"
        " 若日誌僅 127.0.0.1，代表眼鏡封包未到本機。除錯探索請在 server/.env 設 UDP_RECV_LOG=1 後重啟。"
    )
    if getattr(config, "ASR_WHISPER_WARMUP", True):

        def _warm_whisper() -> None:
            try:
                from local_whisper_asr import warmup_whisper

                warmup_whisper()
                print("[ASR] Whisper warmup finished.")
            except Exception as e:
                print(f"[ASR] Whisper warmup skipped: {e}")

        threading.Thread(target=_warm_whisper, daemon=True).start()
    print(
        "[提示] 關閉時若出現 Waiting for connections：先關閉正在看 /stream 的瀏覽器分頁，"
        "或再按一次 Ctrl+C 強制結束。"
    )
    yield
    stream_manager.shutdown_for_exit()
    _yolo_stop.set()
    _nav_stop.set()
    _vision_stop.set()
    _asr_executor.shutdown(wait=False, cancel_futures=True)
    _gemini_executor.shutdown(wait=False, cancel_futures=True)
    _line_ai_executor.shutdown(wait=False, cancel_futures=True)


app = FastAPI(title="Smart Blind Glasses Server", lifespan=lifespan)
app.include_router(line_bot_router)
app.include_router(
    create_monitor_router(
        _monitor_state,
        _monitor_events,
        _get_latest_viewer_frame_bytes,
        get_health_fn=lambda: _server_health.snapshot(),
        get_latency_fn=lambda: {
            "stats": _server_health.latency.stats(),
            "recent": _server_health.latency.recent(20),
        },
    )
)


_DEVICE_API_TOKEN = (getattr(config, "DEVICE_API_TOKEN", "") or "").strip()

_DEVICE_TOKEN_PROTECTED_PATHS = frozenset(
    {
        "/api/gemini",
        "/api/asr",
        "/api/imu",
        "/api/gps",
        "/api/frame",
        "/api/family/emergency",
    }
)


@app.middleware("http")
async def device_token_guard(request: Request, call_next):
    """若設定了 DEVICE_API_TOKEN，則對裝置 API 要求帶 X-Device-Token header。"""
    if _DEVICE_API_TOKEN and request.url.path in _DEVICE_TOKEN_PROTECTED_PATHS:
        token = request.headers.get("X-Device-Token", "")
        if token != _DEVICE_API_TOKEN:
            return _api_error("unauthorized", 401)
    response = await call_next(request)
    return response


@app.middleware("http")
async def capture_esp32_ip(request: Request, call_next):
    """韌體 API：先讀 X-Device-Stream-Url（雲端反代時不可依 client IP 組 :81/stream），再處理請求，最後再記錄 IP。"""
    if _should_record_esp32_ip_from_request(request):
        raw_hdr = request.headers.get("X-Device-Stream-Url")
        if raw_hdr is not None:
            u = _safe_device_stream_url(raw_hdr)
            if u:
                stream_manager.set_device_pull_url(u)
            elif raw_hdr.strip():
                print("[ESP32] Ignored invalid X-Device-Stream-Url header")
    response = await call_next(request)
    if _should_record_esp32_ip_from_request(request) and not stream_manager.get_device_pull_url():
        _record_esp32_ip_from_request(request)
    return response


@app.get("/health", response_model=None)
async def health() -> dict:
    """健康檢查，ESP32 可確認伺服器在線。"""
    return {"status": "ok", "server_ip": _get_local_ip()}


@app.get("/")
async def root() -> str:
    return "Smart Blind Glasses API. Use /health, /api/gemini, /audio/latest, /monitor, /stream."


@app.get("/stream", response_model=None)
async def public_mjpeg_stream_proxy(request: Request):
    """
    公開 MJPEG：（1）若 .env 設 ESP32_STREAM_URL 且非指向本機 /stream 迴圈，轉發上游；
    （2）否則用 stream_manager 已快取之 JPEG 組 multipart MJPEG。
    伺服器取得畫面仍靠背景拉流（LAN、X-Device-Stream-Url、或 ESP32_STREAM_URL），
    不必為了「餵畫面」而另外開瀏覽器常駐某頁。
    """
    upstream = (getattr(config, "ESP32_STREAM_URL", "") or "").strip()
    rh = (request.headers.get("host") or "").strip()
    use_proxy = bool(upstream) and not _is_recursive_esp32_stream_proxy(upstream, rh)

    if use_proxy:

        def _open_upstream() -> requests.Response:
            return requests.get(upstream, stream=True, timeout=30)  # type: ignore[no-any-return]

        try:
            r = await asyncio.to_thread(_open_upstream)
            r.raise_for_status()
        except requests.RequestException as e:
            return JSONResponse(
                {"ok": False, "error": "upstream_failed", "detail": str(e)},
                status_code=502,
            )

        def gen():
            try:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        yield chunk
            finally:
                r.close()

        ct = r.headers.get("Content-Type") or "multipart/x-mixed-replace; boundary=frame"
        return StreamingResponse(gen(), media_type=ct)

    async def cache_gen():
        boundary = b"frame"
        while True:
            frame_b, _ = stream_manager.get_latest_frame()
            if frame_b:
                yield (
                    b"--"
                    + boundary
                    + b"\r\nContent-Type: image/jpeg\r\nContent-Length: "
                    + str(len(frame_b)).encode()
                    + b"\r\n\r\n"
                    + frame_b
                    + b"\r\n"
                )
            await asyncio.sleep(_STREAM_CACHE_MJPEG_INTERVAL_SEC)

    return StreamingResponse(
        cache_gen(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.head("/stream", response_model=None)
async def public_mjpeg_stream_proxy_head() -> Response:
    return Response(
        status_code=200,
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/monitor")
async def monitor_page():
    path = os.path.join(os.path.dirname(__file__), "static", "monitor.html")
    if not os.path.exists(path):
        return _api_error("monitor_page_not_found", 404)
    return FileResponse(path, media_type="text/html")


@app.get("/monitor/vendor/three.module.js")
async def monitor_three_module():
    path = os.path.join(os.path.dirname(__file__), "static", "vendor", "three.module.js")
    if not os.path.exists(path):
        return _api_error("three_module_not_found", 404)
    return FileResponse(path, media_type="application/javascript")


@app.get("/monitor/imu")
async def imu_monitor_page():
    path = os.path.join(os.path.dirname(__file__), "static", "imu_monitor.html")
    if not os.path.exists(path):
        return _api_error("imu_monitor_page_not_found", 404)
    return FileResponse(path, media_type="text/html")


@app.websocket("/ws/viewer")
async def ws_viewer(ws: WebSocket):
    """推送最新 JPEG 影像給瀏覽器。"""
    await ws.accept()
    ws_broadcaster.track_client(ws_broadcaster.viewer_clients, ws)
    last_sent_frame: Optional[bytes] = None
    try:
        while True:
            frame_b = _get_latest_viewer_frame_bytes()
            # 若畫面未更新就不重送，降低網路與瀏覽器解碼負載。
            if frame_b and frame_b is not last_sent_frame:
                await ws.send_bytes(frame_b)
                last_sent_frame = frame_b
            # 預設約 20fps，降低 CPU/頻寬占用，讓 API 回應更穩。
            await asyncio.sleep(_viewer_ws_interval_sec)
    except WebSocketDisconnect:
        pass
    finally:
        ws_broadcaster.untrack_client(ws_broadcaster.viewer_clients, ws)


@app.websocket("/ws_ui")
async def ws_ui(ws: WebSocket):
    """推送監控狀態（JSON）。"""
    await ws.accept()
    ws_broadcaster.track_client(ws_broadcaster.ui_clients, ws)
    try:
        while True:
            state = _monitor_state()
            await ws.send_json(state)
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    finally:
        ws_broadcaster.untrack_client(ws_broadcaster.ui_clients, ws)


@app.websocket("/ws")
async def ws_imu(ws: WebSocket):
    """
    IMU 相容端點：
    - 若來自 ESP32：接收 JSON 並更新融合狀態（等同 /api/imu）
    - 同時把 fusion snapshot 回推給連線端（方便前端即時顯示）
    """
    await ws.accept()
    ws_broadcaster.track_client(ws_broadcaster.imu_clients, ws)
    fusion = get_fusion()
    try:
        while True:
            # 先嘗試接收（不阻塞太久），避免送出 snapshot 被卡住
            try:
                data = await asyncio.wait_for(ws.receive_json(), timeout=0.1)
                fusion.update_imu(data)
            except asyncio.TimeoutError:
                pass
            except WebSocketDisconnect:
                raise
            except Exception:
                # 收到非預期格式則忽略，避免影響前端顯示
                pass

            await ws.send_json(fusion.get_snapshot())
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    finally:
        ws_broadcaster.untrack_client(ws_broadcaster.imu_clients, ws)


@app.get("/api/obstacle")
async def api_obstacle() -> dict:
    """回傳目前 YOLO 避障分析結果（若有）。"""
    with _obstacle_lock:
        text = _latest_obstacle_text
    return {"obstacle": text}


@app.post("/api/gemini")
async def api_gemini(request: Request) -> dict:
    """
    依目前最新影格做 Gemini 場景分析，並將描述文字送入 TTS 佇列。
    ESP32 按鍵觸發 POST 即可。
    """
    import uuid as _uuid
    rid = f"gemini-{_uuid.uuid4().hex[:8]}"
    _server_health.latency.begin(rid, "arrive")

    frame_b = _get_latest_frame_bytes()
    if not frame_b:
        return _api_error("no_frame", 404)
    if not _gemini_job_sem.acquire(blocking=False):
        _server_health.set_error("gemini:server_busy")
        lat = _server_health.latency.finish(rid, "rejected")
        return JSONResponse({"ok": False, "error": "server_busy", "latency_ms": lat}, status_code=503)
    mode = request.query_params.get("mode", "general")
    _server_health.latency.mark(rid, "pre_inference")
    loop = asyncio.get_running_loop()
    try:
        text = await loop.run_in_executor(
            _gemini_executor,
            lambda: analyze_scene(frame_b, extra_prompt=f"（模式：{mode}）"),
        )
        _server_health.latency.mark(rid, "post_inference")
        ok = tts_enqueue(text)
        lat = _server_health.latency.finish(rid, "tts_enqueued")
        return {"ok": True, "queued": ok, "latency_ms": lat}
    finally:
        _gemini_job_sem.release()


@app.get("/audio/latest")
async def audio_latest(request: Request):
    """回傳最新 TTS 產生的語音檔（edge-tts 輸出），供 ESP32 下載播放。"""
    path = tts_latest_path()
    if not path:
        return _api_error("no_audio", 404)
    path = os.path.abspath(path)
    if not os.path.exists(path):
        return _api_error("no_audio", 404)
    seq = tts_current_seq()
    etag = f'"{seq}"'
    inm = request.headers.get("if-none-match")
    if inm and inm.strip() == etag:
        return Response(
            status_code=304,
            headers={
                "ETag": etag,
                "X-Audio-Seq": str(seq),
                "Cache-Control": "private, max-age=0, must-revalidate",
            },
        )
    resp = FileResponse(path, media_type="audio/mpeg")
    resp.headers["X-Audio-Seq"] = str(seq)
    resp.headers["ETag"] = etag
    resp.headers["Cache-Control"] = "private, max-age=0, must-revalidate"
    return resp


@app.post("/api/asr")
async def api_asr(request: Request) -> dict:
    """
    ESP32 上傳語音 WAV：
    - 多意圖分類
    - 路由到導航/停止/場景描述/找物品/紅綠燈流程
    """
    import uuid as _uuid
    rid = f"asr-{_uuid.uuid4().hex[:8]}"
    _server_health.latency.begin(rid, "arrive")

    body = await request.body()
    _server_health.latency.mark(rid, "body_read")
    loop = asyncio.get_running_loop()

    sync_param = (request.query_params.get("sync", "") or "").strip().lower()
    force_sync = sync_param in ("1", "true", "yes", "on")
    run_async = _asr_default_async and not force_sync

    if not _asr_job_sem.acquire(blocking=False):
        if run_async and _asr_wait_queue_max > 0:
            dropped = 0
            with _asr_wait_lock:
                while len(_asr_wait_queue) >= _asr_wait_queue_max:
                    _asr_wait_queue.popleft()
                    dropped += 1
                _asr_wait_queue.append(body)
            lat = _server_health.latency.finish(rid, "queued")
            return JSONResponse(
                {
                    "ok": True,
                    "accepted": True,
                    "queued": True,
                    "dropped": dropped,
                    "latency_ms": lat,
                },
                status_code=202,
            )
        _server_health.set_error("asr:server_busy")
        lat = _server_health.latency.finish(rid, "rejected")
        return JSONResponse(
            {"ok": False, "error": "server_busy", "latency_ms": lat},
            status_code=503,
        )

    runner = _build_asr_runner(body)

    if run_async:

        async def _bg_process_asr() -> None:
            try:
                intent = await loop.run_in_executor(_asr_executor, runner)
                _push_voice_intent(intent)
                _server_health.latency.finish(rid, "bg_done")
            except Exception as e:
                _server_health.set_error(f"asr_bg:{e}")
            finally:
                _asr_job_sem.release()
                await _asr_schedule_next_from_queue()

        asyncio.create_task(_bg_process_asr())
        lat = _server_health.latency.finish(rid, "accepted")
        return JSONResponse(
            {"ok": True, "accepted": True, "queued": False, "latency_ms": lat},
            status_code=202,
        )

    try:
        intent = await loop.run_in_executor(_asr_executor, runner)
        _server_health.latency.mark(rid, "intent_done")
        _push_voice_intent(intent)
        lat = _server_health.latency.finish(rid, "response")
        return {"ok": True, "intent": intent, "accepted": False, "queued": False, "latency_ms": lat}
    finally:
        _asr_job_sem.release()


@app.post("/api/frame")
async def api_frame(request: Request):
    """ESP32 主動推送 JPEG 幀（Frame Push），不需伺服器拉 MJPEG。"""
    body = await request.body()
    if not body:
        return _api_error("empty_body", 400)
    stream_manager.set_frame(body)
    return {"ok": True}


@app.post("/api/imu")
async def api_imu(request: Request) -> dict:
    """ESP32 上傳 IMU 資料。"""
    try:
        data = await request.json()
    except Exception as e:
        _server_health.set_error(f"imu:invalid_json:{e}")
        return _api_error("invalid_json", 400)
    try:
        get_fusion().update_imu(data)
        _server_health.touch_imu()
        ev = _event_engine.update_imu(data)
        notify_event = ev.get("notify_event")
        if notify_event and _event_engine.should_send_line():
            _notify_family_text(str(notify_event.get("text") or "警示：偵測到異常事件。"))
            _notify_family_location()
    except Exception as e:
        _server_health.set_error(f"imu:{e}")
        _log_exception("api_imu", e)
        return _api_error("imu_processing_failed", 500)
    return {"ok": True}


def _update_last_gps(
    lat: float,
    lng: float,
    alt: Optional[float] = None,
    sat: Optional[int] = None,
    course: Optional[float] = None,
) -> None:
    """Thread-safe 更新最後已知位置。"""
    global _last_gps
    with _gps_lock:
        _last_gps = {"lat": lat, "lng": lng, "ts": time.time(), "alt": alt, "sat": sat, "course": course}


def _get_last_gps(max_age_sec: float) -> Optional[dict]:
    """取得最後已知 GPS；若超過 max_age_sec 或不存在則回傳 None。"""
    with _gps_lock:
        gps = _last_gps
    if not gps or (time.time() - gps.get("ts", 0)) > max_age_sec:
        return None
    return gps


@app.post("/api/gps")
async def api_gps(request: Request) -> dict:
    """ESP32 上傳 GPS 資料；儲存為導航起點並更新 IMU/GPS 融合。"""
    try:
        data = await request.json()
    except Exception as e:
        _server_health.set_error(f"gps:invalid_json:{e}")
        return _api_error("invalid_json", 400)
    try:
        lat = data.get("lat")
        lng = data.get("lng")
        if lat is None or lng is None:
            return _api_error("missing_lat_lng", 400)
        latf = float(lat)
        lngf = float(lng)
        course = data.get("course")
        _update_last_gps(latf, lngf, data.get("alt"), data.get("sat"), course)
        get_fusion().update_gps(latf, lngf, course=course)
        _event_engine.update_gps(data)
        _server_health.touch_gps()
    except Exception as e:
        _server_health.set_error(f"gps:{e}")
        _log_exception("api_gps", e)
        return _api_error("gps_processing_failed", 500)
    return {"ok": True}


@app.get("/api/family/location")
async def api_family_location() -> dict:
    snap = _event_engine.get_snapshot()
    gps = snap.get("last_gps") or {}
    return {
        "ok": True,
        "lat": gps.get("lat"),
        "lng": gps.get("lng"),
        "map_url": gps.get("map_url") or "",
        "ts": gps.get("ts"),
    }


@app.get("/api/family/status")
async def api_family_status() -> dict:
    snap = _event_engine.get_snapshot()
    line_ok = _line_notifier.is_ready()
    return {"ok": True, "line_ready": line_ok, "snapshot": snap}


@app.post("/api/family/emergency")
async def api_family_emergency(request: Request) -> dict:
    note = ""
    try:
        body = await request.json()
        note = str(body.get("note") or "")
    except Exception as e:
        _log_exception("api_family_emergency", e)
        return _api_error("invalid_json", 400)
    ev = _event_engine.emergency_event(note)
    sent = False
    if _event_engine.should_send_line():
        _notify_family_text(str(ev.get("text") or "緊急通知"))
        _notify_family_location()
        sent = True
    return {"ok": True, "sent": sent, "event": ev}


@app.post("/api/line/webhook")
async def api_line_webhook(request: Request):
    """
    LINE webhook：
    - 快捷：位置 / 狀態 / 緊急（家屬手動通報，與眼鏡語音求救分開）
    - 其餘文字：Gemini 家屬助理（無 key 時 fallback 提示）
    """
    body = await request.body()
    sig = request.headers.get("X-Line-Signature", "")
    secret = (getattr(config, "LINE_CHANNEL_SECRET", "") or "").strip()
    if secret:
        mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
        expected = base64.b64encode(mac).decode("utf-8")
        if not hmac.compare_digest(expected, sig):
            return _api_error("invalid_signature", 401)

    try:
        payload = await request.json()
    except Exception as e:
        _log_exception("line_webhook_json", e)
        return _api_error("invalid_json", 400)

    events = payload.get("events") or []
    loop = asyncio.get_running_loop()
    for ev in events:
        if ev.get("type") != "message":
            continue
        message = ev.get("message") or {}
        if message.get("type") != "text":
            continue
        raw_text = str(message.get("text") or "").strip()
        text = raw_text.lower()
        reply_token = str(ev.get("replyToken") or "")
        if not reply_token:
            continue
        if text in ("位置", "定位", "where", "location"):
            _line_notifier.reply_text(reply_token, _build_family_location_text())
        elif text in ("狀態", "status"):
            _line_notifier.reply_text(reply_token, _build_family_status_text())
        elif text in ("緊急", "emergency", "sos"):
            _event_engine.emergency_event("line_manual")
            if _event_engine.should_send_line():
                _notify_family_text("【家屬手動緊急】有人於 LINE 觸發緊急通報，請確認是否誤觸並聯繫使用者。")
                _notify_family_location()
            _line_notifier.reply_text(
                reply_token,
                "已送出「家屬手動」緊急通報（與眼鏡語音求救不同）。若為誤觸請向家屬說明。",
            )
        else:
            ctx = _line_gemini_context()
            ai = await loop.run_in_executor(
                _line_ai_executor,
                lambda r=raw_text, c=ctx: family_line_reply(r, c),
            )
            out = (ai or "").strip()
            if not out:
                out = (
                    "我暫時無法使用 AI 回覆。請用下方快捷鍵：「位置」「狀態」；"
                    "「緊急通報」僅供家屬手動送出警訊。"
                )
            _line_notifier.reply_text(reply_token, out)
    return {"ok": True}


@app.post("/api/gpio_test")
async def api_gpio_test(request: Request) -> dict:
    """
    ESP32 D8->D2 loopback 測試用：
    - 每 5 秒回報一次 ok 狀態
    - 讓你在伺服器端清楚看到是否有收到
    """
    try:
        data = await request.json()
    except Exception as e:
        _log_exception("api_gpio_test", e)
        data = {}
    ok = bool(data.get("ok"))
    client = request.client.host if request.client else "unknown"
    print(f"[GPIO_TEST] from {client} ok={ok}")
    return {"ok": True, "received": ok, "ts": time.time()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=config.HTTP_HOST,
        port=config.HTTP_PORT,
        reload=False,
        log_level="warning",
        access_log=False,
    )
