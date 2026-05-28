"""
智慧導盲眼鏡 - FastAPI 伺服器
通訊與即時影像、UDP 發現、YOLO 避障、Gemini / TTS、導航狀態機、監控介面。
"""

import asyncio
import base64
import hashlib
import hmac
import os
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Dict, List, Optional

import cv2  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect  # type: ignore[import-untyped]
from fastapi.responses import FileResponse, JSONResponse  # type: ignore[import-untyped]

import config
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
from tts_queue import (
    enqueue as tts_enqueue,
    get_latest_path as tts_latest_path,
    get_current_seq as tts_current_seq,
)
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
# 注意：使用者要求保留原本 Line 邏輯，但為了程式碼完整性我們仍保留 executor 定義但不強制切換
_line_ai_executor = ThreadPoolExecutor(
    max_workers=max(1, int(getattr(config, "LINE_AI_EXECUTOR_MAX_WORKERS", 2))),
    thread_name_prefix="line-ai",
)

_viewer_ws_interval_sec = max(0.01, float(getattr(config, "VIEWER_WS_INTERVAL_SEC", 0.05)))
_asr_default_async = bool(getattr(config, "ASR_DEFAULT_ASYNC", True))
# API 併發控制：同時處理中的 ASR / Gemini 任務上限
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
        "/audio/latest",
    }
)


def _should_record_esp32_ip_from_request(request: Request) -> bool:
    return request.url.path in _ESP32_IP_FROM_REQUEST_PATHS


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


def _build_asr_runner(audio_body: bytes):
    """回傳可在 executor 中執行的同步 callable（將 bytes 綁定）。"""

    def _run() -> str:
        return handle_asr_and_route(
            audio_body,
            tts_enqueue_fn=tts_enqueue,
            get_last_gps_fn=_get_last_gps,
            request_scene_desc_fn=lambda: _request_scene_desc("general"),
            request_traffic_light_fn=lambda: get_controller().start(),
            start_nav_fn=lambda: start_navigation_to_home(
                tts_enqueue, _get_last_gps, config.LAST_GPS_MAX_AGE_SEC
            ),
            stop_nav_fn=lambda: stop_navigation(tts_enqueue),
            start_item_search_fn=lambda target: _start_item_search(target or ""),
            stop_item_search_fn=_stop_item_search,
            on_distress_fn=_handle_voice_distress,
            max_gps_age_sec=config.LAST_GPS_MAX_AGE_SEC,
        )

    return _run


async def _asr_schedule_next_from_queue() -> None:
    """當 ASR 槽位釋放後，嘗試處理佇列中下一筆。"""
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
    import uuid

    rid = f"asr-q-{uuid.uuid4().hex[:8]}"
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


def _push_voice_intent(text: str) -> None:
    with _voice_lock:
        _recent_voice_intents.append({"ts": str(time.time()), "text": text})
        if len(_recent_voice_intents) > 20:
            del _recent_voice_intents[:-20]


def _get_latest_frame_bytes() -> Optional[bytes]:
    frame_b, _ = stream_manager.get_latest_frame()
    if not frame_b or not stream_manager.has_recent_frame():
        return None
    return frame_b


def _get_latest_viewer_frame_bytes() -> Optional[bytes]:
    """給前端顯示的影像：優先 annotated，否則 fallback raw。"""
    try:
        annotated = _vision_controller.get_latest_annotated_frame_bytes()
        if annotated:
            return annotated
    except Exception:
        pass
    return _get_latest_frame_bytes()


def _request_scene_desc(mode: str = "general") -> None:
    frame_b = _get_latest_frame_bytes()
    if not frame_b:
        tts_enqueue("目前沒有可用畫面。")
        return
    text = analyze_scene(frame_b, extra_prompt=f"（模式：{mode}）")
    tts_enqueue(text)


def _notify_family_event(text: str, event_type: str = "emergency") -> None:
    gps = _event_engine.get_snapshot().get("last_gps") or {}
    lat = gps.get("lat")
    lng = gps.get("lng")
    
    if event_type == "fall":
        title = "家人智慧眼鏡：疑似跌倒定位"
        address = "請點擊此處查看家人的即時地圖位置與導航。"
    else:
        title = "家人智慧眼鏡：緊急求助定位"
        address = "請點擊此處查看家人的即時地圖位置與導航。"

    if lat is not None and lng is not None:
        try:
            _line_notifier.push_text_and_location(
                text=text,
                title=title,
                address=address,
                lat=float(lat),
                lng=float(lng),
            )
        except Exception:
            pass
    else:
        try:
            _line_notifier.push_text(text)
        except Exception:
            pass


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
        _notify_family_event(text=msg, event_type="emergency")
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
                pass
        time.sleep(_yolo_interval_sec)
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
        except Exception:
            pass
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

        except Exception:
            pass

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
    return {
        "mode": nav_session.get_state().value,
        "navigation": nav_session.get_snapshot(),
        "fusion": fusion.get_snapshot(),
        "traffic_light": crossing.get_state(),
        "item_search": get_item_search_snapshot(),
        "recent_voice": recent_voice,
        "esp32_ip": stream_manager.get_esp32_ip(),
        "family": _event_engine.get_snapshot(),
        "server_health": _server_health.snapshot(),
    }


def _monitor_events(limit: int) -> List[Dict[str, object]]:
    return get_nav_session().get_recent_events(limit=limit)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 雲端部署：通常 UDP discovery 不通，因此可用 ENABLE_UDP_DISCOVERY / ESP32_STREAM_URL 控制行為
    esp32_stream_url = (getattr(config, "ESP32_STREAM_URL", "") or "").strip()
    enable_udp = bool(getattr(config, "ENABLE_UDP_DISCOVERY", True))

    if enable_udp and not esp32_stream_url:
        start_udp_listener_thread(on_esp32_seen=stream_manager.set_esp32_ip)

    # 若已提供可被雲端存取的串流 URL，就先啟動 MJPEG puller（不依賴 UDP）。
    if esp32_stream_url and not stream_manager.get_esp32_ip():
        stream_manager.set_esp32_ip("esp32-stream-url")

    # ASR 預載（降低第一次辨識延遲）
    if getattr(config, "ASR_WHISPER_WARMUP", True):
        def _warm_whisper() -> None:
            try:
                from local_whisper_asr import warmup_whisper
                warmup_whisper()
                print("[ASR] Whisper warmup finished.")
            except Exception as e:
                print(f"[ASR] Whisper warmup skipped: {e}")

        threading.Thread(target=_warm_whisper, daemon=True).start()

    yolo_thread = threading.Thread(target=_yolo_worker, daemon=True)
    nav_thread = threading.Thread(target=_nav_worker, daemon=True)
    vision_thread = threading.Thread(target=_vision_worker, daemon=True)
    yolo_thread.start()
    if not _VISION_DRIVE_ENABLED:
        nav_thread.start()
    vision_thread.start()
    print(
        "[提示] 陀螺儀三軸／加速度是 HTTP POST /api/imu，不是 UDP；UDP 只有「找伺服器」(WHO_IS_SERVER)。"
        " 若日誌僅 127.0.0.1，代表眼鏡封包未到本機。除錯探索請在 server/.env 設 UDP_RECV_LOG=1 後重啟。"
    )
    yield
    _yolo_stop.set()
    _nav_stop.set()
    _vision_stop.set()
    _asr_executor.shutdown(wait=False)
    _gemini_executor.shutdown(wait=False)
    _line_ai_executor.shutdown(wait=False)


app = FastAPI(title="Smart Blind Glasses Server", lifespan=lifespan)
app.include_router(line_bot_router)
app.include_router(
    create_monitor_router(
        _monitor_state,
        _monitor_events,
        _get_latest_viewer_frame_bytes,
        get_health_fn=lambda: _server_health.snapshot(),
    )
)


@app.middleware("http")
async def capture_esp32_ip(request: Request, call_next):
    """僅在韌體會呼叫的 API 上記錄客戶端 IP，供拉取 MJPEG（避免誤用 LINE/瀏覽器 IP）。"""
    response = await call_next(request)
    if _should_record_esp32_ip_from_request(request):
        _record_esp32_ip_from_request(request)
    return response


@app.get("/health", response_model=None)
async def health() -> dict:
    """健康檢查，ESP32 可確認伺服器在線。"""
    return {"status": "ok", "server_ip": _get_local_ip()}


@app.get("/")
async def root() -> str:
    return "Smart Blind Glasses API. Use /health, /api/gemini, /audio/latest, /monitor."


@app.get("/monitor")
async def monitor_page():
    path = os.path.join(os.path.dirname(__file__), "static", "monitor.html")
    if not os.path.exists(path):
        return JSONResponse({"error": "monitor_page_not_found"}, status_code=404)
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
            # 預設約 20fps，降低 CPU/頻寬占用
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
    import uuid

    rid = f"gemini-{uuid.uuid4().hex[:8]}"
    _server_health.latency.begin(rid, "arrive")

    frame_b = _get_latest_frame_bytes()
    if not frame_b:
        return {"ok": False, "error": "no_frame"}

    if not _gemini_job_sem.acquire(blocking=False):
        _server_health.set_error("gemini:server_busy")
        lat = _server_health.latency.finish(rid, "rejected")
        return JSONResponse(
            {"ok": False, "error": "server_busy", "latency_ms": lat},
            status_code=503,
        )

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
        return JSONResponse({"error": "no_audio"}, status_code=404)
    path = os.path.abspath(path)
    if not os.path.exists(path):
        return JSONResponse({"error": "no_audio"}, status_code=404)

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
    import uuid

    rid = f"asr-{uuid.uuid4().hex[:8]}"
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
        return {
            "ok": True,
            "intent": intent,
            "accepted": False,
            "queued": False,
            "latency_ms": lat,
        }
    finally:
        _asr_job_sem.release()


@app.post("/api/imu")
async def api_imu(request: Request) -> dict:
    """ESP32 上傳 IMU 資料。"""
    try:
        data = await request.json()
        get_fusion().update_imu(data)
        _server_health.touch_imu()
        ev = _event_engine.update_imu(data)
        notify_event = ev.get("notify_event")
        if notify_event and _event_engine.should_send_line():
            _notify_family_event(
                text=str(notify_event.get("text") or "警示：偵測到異常事件。"),
                event_type="fall"
            )
    except Exception as e:
        _server_health.set_error(f"imu:{e}")
        pass
    return {"ok": True}


_current_device_status: dict = {}

@app.post("/api/status")
async def api_post_status(request: Request) -> dict:
    """接收來自配戴者 App 轉發的藍牙設備狀態。"""
    global _current_device_status
    try:
        _current_device_status = await request.json()
    except Exception:
        pass
    return {"status": "success"}

@app.get("/api/status")
async def api_get_status() -> dict:
    """提供家屬端 App 取得最新設備狀態與 GPS。"""
    resp = dict(_current_device_status)
    # 把伺服器接收到的最新 ESP32 GPS 一併塞進去回傳
    with _gps_lock:
        if _last_gps:
            resp["gps"] = _last_gps
    return resp


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
        lat = data.get("lat")
        lng = data.get("lng")
        if lat is not None and lng is not None:
            latf = float(lat)
            lngf = float(lng)
            course = data.get("course")
            _update_last_gps(latf, lngf, data.get("alt"), data.get("sat"), course)
            get_fusion().update_gps(latf, lngf, course=course)
            _event_engine.update_gps(data)
            _server_health.touch_gps()
    except Exception as e:
        _server_health.set_error(f"gps:{e}")
        pass
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
    except Exception:
        pass
    ev = _event_engine.emergency_event(note)
    sent = False
    if _event_engine.should_send_line():
        _notify_family_event(
            text=str(ev.get("text") or "緊急通知：眼鏡端觸發緊急求助。"),
            event_type="emergency"
        )
        sent = True
    return {"ok": True, "sent": sent, "event": ev}



@app.post("/api/gpio_test")
async def api_gpio_test(request: Request) -> dict:
    """
    ESP32 D8->D2 loopback 測試用：
    - 每 5 秒回報一次 ok 狀態
    - 讓你在伺服器端清楚看到是否有收到
    """
    try:
        data = await request.json()
    except Exception:
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
    )
