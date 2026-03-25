"""
智慧導盲眼鏡 - 最終整合監控版
整合：極簡化影像監控、連續導航狀態機、多語音意圖路由、IMU+GPS 融合、紅綠燈監控。
"""

from line_bot import handler  # 引入你在 line_bot.py 定義好的 handler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from line_bot import line_bot_api # 也要引入這個來回話

import asyncio
import os
import threading
import time
from contextlib import asynccontextmanager
from typing import Dict, List, Optional

import cv2
import numpy as np
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse, StreamingResponse

import config
from gemini_client import analyze_scene
from imu_gps_fusion import get_fusion
from intent_router import handle_asr_and_route
from navigation import start_navigation_to_home, stop_navigation, tick_navigation
from navigation_state import NavState, get_nav_session
from stream_manager import stream_manager
from traffic_crossing import get_controller
from udp_discovery import _get_local_ip, start_udp_listener_thread
from yolo_detector import get_detector
from tts_queue import enqueue as tts_enqueue, get_latest_path as tts_latest_path

# --- 全域狀態與背景任務標記 ---
_obstacle_lock = threading.Lock()
_latest_obstacle_text: Optional[str] = "前方無障礙物"

_gps_lock = threading.Lock()
_last_gps: Optional[dict] = None

_voice_lock = threading.Lock()
_last_intent_text = "等待語音指令..."

_yolo_stop = threading.Event()
_nav_stop = threading.Event()

def _get_latest_frame_bytes() -> Optional[bytes]:
    frame_b, _ = stream_manager.get_latest_frame()
    if not frame_b or not stream_manager.has_recent_frame():
        return None
    return frame_b

# --- 背景 Worker 實作 ---

def _yolo_worker() -> None:
    """功能 4：紅綠燈與避障偵測核心循環"""
    global _latest_obstacle_text
    det = get_detector()
    while not _yolo_stop.is_set():
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
            except Exception: pass
        time.sleep(0.2)

def _nav_worker() -> None:
    """功能 1 & 4：導航狀態機 tick 與 紅綠燈過馬路邏輯"""
    nav_session = get_nav_session()
    crossing = get_controller()
    while not _nav_stop.is_set():
        try:
            # 功能 1：處理導航中、重規劃、到點提醒
            tick_navigation(tts_enqueue, _get_last_gps, config.LAST_GPS_MAX_AGE_SEC)
            
            # 功能 4：處理紅綠燈偵測與「可通行」語音提示
            crossing.tick(_get_latest_frame_bytes, tts_enqueue)
            
            # 同步狀態到 Session
            c_state = crossing.get_state().get("state")
            if c_state == "wait":
                nav_session.set_state(NavState.CROSSING_WAIT)
            elif c_state in ("go", "recheck"):
                nav_session.set_state(NavState.CROSSING_GO)
        except Exception: pass
        time.sleep(1.5)

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_udp_listener_thread(on_esp32_seen=stream_manager.set_esp32_ip)
    threading.Thread(target=_yolo_worker, daemon=True).start()
    threading.Thread(target=_nav_worker, daemon=True).start()
    yield
    _yolo_stop.set()
    _nav_stop.set()

app = FastAPI(title="Smart Blind Glasses Server", lifespan=lifespan)


@app.post("/callback")
async def callback(request: Request):
    # 這是給 LINE 伺服器驗證身分用的
    signature = request.headers.get("X-Line-Signature")
    body = (await request.body()).decode("utf-8")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        return JSONResponse(content={"detail": "Invalid signature"}, status_code=400)

    return "OK"

# 當有人傳文字訊息來時，要執行什麼動作
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text
    
    # 1. 判斷要做什麼功能
    if "位置" in msg or "在哪" in msg:
        gps = _get_last_gps(max_age_sec=30)
        if gps:
            res = f"📍 使用者目前位置：\nhttps://www.google.com/maps?q={gps['lat']},{gps['lng']}"
        else:
            res = "目前定位中，請稍候再試。"
            
    elif "看看" in msg or "環境" in msg:
        description = analyze_scene(_get_latest_frame_bytes())
        res = f"👁️ AI 視覺描述：\n{description}"
        
    elif "狀態" in msg:
        nav_session = get_nav_session()
        res = f"🔋 系統狀態：\n模式：{nav_session.get_state().value}\n最近語音：{_last_intent_text}"
        
    else:
        res = "您好！我是智慧眼鏡助理。\n您可以輸入：\n1.「位置」：查看地點\n2.「看看」：描述現場環境\n3.「狀態」：查看系統運行情況"

    # 2. 只有這一段負責回話，把底下的全部刪掉
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=res)
    )

# --- API 路由實作 ---

@app.get("/api/get_last_status")
async def get_last_status():
    """供網頁前端獲取所有狀態 (含功能 1, 3, 4)"""
    nav_session = get_nav_session()
    gps_data = _get_last_gps(max_age_sec=config.LAST_GPS_MAX_AGE_SEC)
    
    return {
        "gps": gps_data,
        "time": time.strftime("%H:%M:%S", time.localtime()),
        "system": {
            "mode": nav_session.get_state().value, # 導航狀態機
            "last_voice": _last_intent_text,       # 語音意圖
            "nav_step": nav_session.get_snapshot().get("next_step", "無")
        }
    }

@app.post("/api/asr")
async def api_asr(request: Request):
    """功能 2：多語音意圖分類路由"""
    global _last_intent_text
    body = await request.body()
    loop = asyncio.get_event_loop()
    
    # 調用路由處理：導航到家、停止導航、描述畫面、找物品、紅綠燈
    intent = await loop.run_in_executor(
        None,
        lambda: handle_asr_and_route(
            body, tts_enqueue, _get_last_gps, 
            request_scene_desc_fn=lambda: analyze_scene(_get_latest_frame_bytes()),
            request_item_search_fn=lambda: analyze_scene(_get_latest_frame_bytes(), "找尋特定物品"),
            request_traffic_light_fn=lambda: get_controller().start(),
            start_nav_fn=lambda: start_navigation_to_home(tts_enqueue, _get_last_gps, config.LAST_GPS_MAX_AGE_SEC),
            stop_nav_fn=lambda: stop_navigation(tts_enqueue),
            max_gps_age_sec=config.LAST_GPS_MAX_AGE_SEC
        )
    )
    _last_intent_text = intent
    return {"ok": True, "intent": intent}

@app.post("/api/imu")
async def api_imu(request: Request):
    """功能 3：IMU + GPS 融合更新"""
    try:
        data = await request.json()
        get_fusion().update_imu(data)
    except: pass
    return {"ok": True}

@app.get("/api/stream")
async def video_feed():
    """提供即時畫面給網頁"""
    async def frame_generator():
        while True:
            frame = _get_latest_frame_bytes()
            if frame:
                yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            await asyncio.sleep(0.05)
    return StreamingResponse(frame_generator(), media_type="multipart/x-mixed-replace; boundary=frame")

# --- 網頁監控介面 (移除 IMU/紅綠燈方塊，極大化影像) ---
@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard():
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>AI 智慧導盲眼鏡監控系統</title>
        <style>
            body {{ background: #12151a; color: white; font-family: 'Segoe UI', sans-serif; margin: 0; padding: 20px; }}
            .header {{ color: #00e5ff; font-size: 24px; font-weight: bold; text-align: center; margin-bottom: 20px; }}
            .main-layout {{ display: flex; gap: 20px; max-width: 1400px; margin: 0 auto; height: 85vh; }}
            .video-section {{ flex: 3; background: #1c222b; border-radius: 15px; overflow: hidden; position: relative; border: 1px solid #333; }}
            .video-feed {{ width: 100%; height: 100%; object-fit: contain; background: #000; }}
            .info-section {{ flex: 1; display: flex; flex-direction: column; gap: 15px; }}
            .card {{ background: #1c222b; border-radius: 12px; padding: 18px; border-left: 4px solid #00e5ff; }}
            .label {{ color: #8e99a7; font-size: 0.85em; margin-bottom: 5px; }}
            .value {{ font-size: 1.1em; font-weight: bold; }}
            .voice-highlight {{ color: #fbbf24; }}
            #conn-status {{ text-align: center; font-size: 0.8em; margin-top: auto; color: #555; }}
        </style>
    </head>
    <body>
        <div class="header">👓 AI 智慧導盲眼鏡 - 進階監控中心</div>
        <div class="main-layout">
            <div class="video-section">
                <div style="position:absolute; top:10px; left:10px; background:rgba(0,0,0,0.6); padding:5px 12px; border-radius:20px; font-size:0.8em;">LIVE: 第一視角畫面</div>
                <img src="/api/stream" class="video-feed">
            </div>
            <div class="info-section">
                <div class="card">
                    <div class="label">📍 當前座標與時間</div>
                    <div id="gps-val" class="value">定位中...</div>
                    <div id="time-val" style="color:#666; font-size:0.8em; margin-top:5px;">--:--:--</div>
                </div>
                <div class="card">
                    <div class="label">🤖 導航狀態機</div>
                    <div class="label">模式：<span id="mode-val" class="value" style="color:#00e5ff;">讀取中</span></div>
                    <div class="label" style="margin-top:10px;">進度：<span id="step-val" class="value">--</span></div>
                </div>
                <div class="card">
                    <div class="label">🎙️ 最近語音意圖</div>
                    <div id="voice-val" class="value voice-highlight">等待語音指令...</div>
                </div>
                <div id="conn-status">● 伺服器通訊正常</div>
            </div>
        </div>
        <script>
            async function update() {{
                try {{
                    const res = await fetch('/api/get_last_status');
                    const d = await res.json();
                    document.getElementById('mode-val').innerText = d.system.mode;
                    document.getElementById('step-val').innerText = d.system.nav_step;
                    document.getElementById('voice-val').innerText = d.system.last_voice;
                    document.getElementById('time-val').innerText = "最後更新: " + d.time;
                    document.getElementById('gps-val').innerText = d.gps ? d.gps.lat.toFixed(5) + ", " + d.gps.lng.toFixed(5) : "等待 GPS...";
                }} catch(e) {{ }}
            }}
            setInterval(update, 1000);
        </script>
    </body>
    </html>
    """

# --- GPS 輔助函數 ---
def _update_last_gps(lat, lng, alt=None, sat=None, course=None):
    global _last_gps
    with _gps_lock:
        _last_gps = {"lat": lat, "lng": lng, "ts": time.time(), "alt": alt, "sat": sat, "course": course}

def _get_last_gps(max_age_sec):
    with _gps_lock:
        gps = _last_gps
    if not gps or (time.time() - gps.get("ts", 0)) > max_age_sec: return None
    return gps

@app.post("/api/gps")
async def api_gps(request: Request):
    try:
        data = await request.json()
        if data.get("lat") is not None:
            _update_last_gps(float(data["lat"]), float(data["lng"]), data.get("alt"), data.get("sat"), data.get("course"))
            get_fusion().update_gps(float(data["lat"]), float(data["lng"]), course=data.get("course"))
    except: pass
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=config.HTTP_HOST, port=config.HTTP_PORT, reload=False)

