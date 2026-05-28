import json
import os
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    ImageSendMessage,
    LocationMessage,
    LocationSendMessage,
    MessageEvent,
    TextMessage,
    TextSendMessage,
)

import config
from line_bot import handler, line_bot_api
from navigation import start_navigation_to_home
from navigation_state import get_nav_session
from tts_queue import enqueue as tts_enqueue

# 避免和 main 產生循環依賴：在事件函式內才 import main
router = APIRouter()

# 對外網址（用於讓 LINE 抓取快照圖片）
_DEFAULT_BASE_URL = "https://solely-nonrenewable-freddy.ngrok-free.dev"
NGROK_BASE_URL = (getattr(config, "LINE_SNAPSHOT_BASE_URL", "") or _DEFAULT_BASE_URL).rstrip("/")

HOME_LOCATION_FILE = os.path.join(os.path.dirname(__file__), "home_location.json")

def load_home_location():
    if os.path.exists(HOME_LOCATION_FILE):
        try:
            with open(HOME_LOCATION_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"lat": None, "lng": None, "address": None}

def save_home_location(loc):
    try:
        with open(HOME_LOCATION_FILE, "w", encoding="utf-8") as f:
            json.dump(loc, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Error] Failed to save home location: {e}")

_home_location = load_home_location()


@handler.add(MessageEvent, message=LocationMessage)
def handle_location_message(event):
    global _home_location
    _home_location["lat"] = event.message.latitude
    _home_location["lng"] = event.message.longitude
    _home_location["address"] = event.message.address
    save_home_location(_home_location)

    res = (
        "【系統通知】\n"
        "已成功將預設住家位置設定為：\n"
        f"{event.message.address}\n\n"
        "未來觸發「導航回家」時，將以此地址作為目的地。"
    )
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=res))


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    import main

    msg = event.message.text.strip()
    user_id = getattr(event.source, "user_id", "")
    print(f"DEBUG: 收到來自 LINE 的訊息 -> |{msg}| (來自 ID: {user_id})")

    if msg.lower() in ["id", "我的id", "userid", "user_id", "my id"]:
        res = (
            "【您的 LINE User ID】\n"
            f"您的唯一識別碼為：\n{user_id}\n\n"
            "請將此 ID 複製並填入伺服器目錄下的 .env 檔案中。\n"
            "例如：\n"
            f"LINE_TARGET_IDS=\"{user_id}\""
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=res))
        return

    help_text = (
        "【智慧導盲眼鏡 系統選單】\n"
        "請選擇或輸入以下指令以進行操作：\n\n"
        "[1] 查詢位置：獲取設備當下 GPS 座標與地圖連結。\n"
        "[2] 眼鏡畫面：擷取鏡頭當下即時影像。\n"
        "[3] 眼鏡狀態：確認設備連線狀態、目前執行模式與最後指令。\n"
        "[4] 設定住家：透過 LINE 傳送「位置資訊」設定導航目的地。\n\n"
        "如需重新顯示本選單，請輸入「功能」或「選單」。"
    )

    if "查詢位置" in msg or "位置" in msg or "在哪" in msg:
        # 先嘗試取得 60 秒內的即時座標
        gps_live = main._get_last_gps(max_age_sec=60)
        if gps_live:
            map_url = f"https://www.google.com/maps?q={gps_live['lat']},{gps_live['lng']}"
            res = f"【位置資訊】\n定位更新完成。設備目前位置如下：\n{map_url}"
        else:
            # 如果沒有即時座標，尋找 15 分鐘內的最後已知座標
            gps_last_known = main._get_last_gps(max_age_sec=900)
            if gps_last_known:
                age_min = max(1, int((time.time() - gps_last_known.get("ts", time.time())) // 60))
                map_url = f"https://www.google.com/maps?q={gps_last_known['lat']},{gps_last_known['lng']}"
                res = (
                    "【位置資訊】\n"
                    "目前設備可能處於室內或遮蔽處，暫無即時訊號。\n"
                    f"這是設備在 {age_min} 分鐘前最後回報的位置：\n{map_url}"
                )
            else:
                res = "【系統警告】\n目前無法取得有效 GPS 訊號 (超過 15 分鐘未更新)。請確認使用者是否處於室內，或嘗試直接聯絡使用者。"
                
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=res))

    elif "拍攝畫面" in msg or "眼鏡畫面" in msg or "看看" in msg or "環境" in msg:
        frame = main._get_latest_frame_bytes()
        if not frame:
            res = "【系統警告】\n眼鏡鏡頭目前無畫面回傳，可能是設備已待機或網路訊號不佳。"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=res))
        else:
            image_url = f"{NGROK_BASE_URL}/api/line_snapshot?t={int(time.time())}"
            line_bot_api.reply_message(
                event.reply_token,
                [
                    TextSendMessage(text="【影像擷取】\n系統已成功擷取設備即時畫面。"),
                    ImageSendMessage(original_content_url=image_url, preview_image_url=image_url),
                ],
            )

    elif "眼鏡狀態" in msg or "狀態" in msg:
        nav_session = get_nav_session()
        mode = nav_session.get_state().value
        last_voice = main._recent_voice_intents[-1]["text"] if main._recent_voice_intents else "無"

        health = main._server_health.snapshot()
        imu_age = health.get("last_imu_age_sec")
        uptime = health.get("uptime_sec", 0)
        last_error = health.get("last_error", "")
        
        if uptime > 3600:
            uptime_str = f"{int(uptime // 3600)} 小時 {int((uptime % 3600) // 60)} 分鐘"
        elif uptime > 60:
            uptime_str = f"{int(uptime // 60)} 分鐘"
        else:
            uptime_str = f"{int(uptime)} 秒"
            
        battery_str = "未知 (待韌體更新支援)"
        
        if imu_age is None:
            conn_status = "設備尚未連線 (或正在重新啟動)"
        elif imu_age > 30:
            minutes = int(imu_age // 60)
            if minutes > 0:
                conn_status = f"設備已離線 (最後連線: {minutes} 分鐘前)"
            else:
                conn_status = "設備已離線 (最後連線: 剛剛)"
        else:
            conn_status = "正常運作中"

        res = (
            "【設備狀態檢測】\n"
            f"- 眼鏡連線狀態：{conn_status}\n"
            f"- 設備剩餘電量：{battery_str}\n"
            f"- 伺服器運行時間：{uptime_str}\n"
            f"- 目前執行模式：{mode}\n"
            f"- 最後語音指令：{last_voice}\n"
        )
        if last_error:
            res += f"- 最近系統警告：{last_error}\n"

        if conn_status.startswith("正常"):
            res += "\n系統診斷結果：設備運作正常。"
        else:
            res += "\n【系統診斷警告】設備離線，請嘗試聯繫使用者確認安全。"
            
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=res))

    elif "設定住家" in msg or "設定家" in msg:
        current_address = _home_location.get("address")
        if current_address:
            res = (
                "【系統提示】\n"
                f"您目前已設定的住家位置為：\n{current_address}\n\n"
                "若要「更改」住家座標，請直接在 LINE 的輸入框點擊「＋」，選擇「位置資訊」，"
                "然後選取您的新住家地址並送出即可。"
            )
        else:
            res = (
                "【系統提示】\n"
                "您目前「尚未設定」住家位置。\n\n"
                "若要設定住家座標，請直接在 LINE 的輸入框點擊「＋」，選擇「位置資訊」，"
                "然後選取您的住家地址並送出即可。"
            )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=res))

    elif "緊急" in msg or "求助" in msg:
        res = (
            "【系統提示】\n"
            "「緊急求助」為配戴者的主動安全防護機制，僅能由使用者透過語音 (如大喊「救命」) 或設備跌倒偵測自動觸發。\n\n"
            "若您目前與使用者失去聯繫，建議您：\n"
            "1. 點擊「查詢位置」確認最後座標\n"
            "2. 點擊「眼鏡畫面」確認現場狀況\n"
            "3. 嘗試透過一般通話聯繫使用者"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=res))

    elif "功能" in msg or "幫助" in msg or "選單" in msg:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=help_text))

    else:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=help_text))


@router.post("/callback")
async def callback(request: Request):
    """LINE Bot Webhook 接收端"""
    signature = request.headers.get("X-Line-Signature", "")
    body = (await request.body()).decode("utf-8")
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        return JSONResponse({"error": "Invalid signature"}, status_code=400)
    return "OK"


@router.get("/api/line_snapshot")
async def line_snapshot():
    import main

    frame_b = main._get_latest_frame_bytes()
    if not frame_b:
        return JSONResponse({"error": "No frame available"}, status_code=404)
    return Response(content=frame_b, media_type="image/jpeg")
