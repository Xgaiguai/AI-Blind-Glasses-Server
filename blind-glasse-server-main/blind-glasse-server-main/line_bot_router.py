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
# 優先使用 PUBLIC_BASE_URL（Cloudflare 網域），其次 LINE_SNAPSHOT_BASE_URL，最後 fallback ngrok
_DEFAULT_BASE_URL = "https://blind-glasses.org"
NGROK_BASE_URL = (
    getattr(config, "PUBLIC_BASE_URL", "")
    or getattr(config, "LINE_SNAPSHOT_BASE_URL", "")
    or _DEFAULT_BASE_URL
).rstrip("/")

_home_location = {"lat": None, "lng": None, "address": None}


@handler.add(MessageEvent, message=LocationMessage)
def handle_location_message(event):
    global _home_location
    _home_location["lat"] = event.message.latitude
    _home_location["lng"] = event.message.longitude
    _home_location["address"] = event.message.address

    res = (
        "🏠 系統已成功將住家位置設定為：\n"
        f"「{event.message.address}」\n\n"
        "未來只要按下「導航回家」，就會引導使用者回到這個地方喔！"
    )
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=res))


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    import main

    msg = event.message.text.strip()
    print(f"DEBUG: 收到來自 LINE 的訊息 -> |{msg}|")

    help_text = (
        "您好！我是導盲眼鏡的小幫手 🦉\n"
        "以下是您可以隨時輸入的關鍵字，或點擊圖文選單來使用的功能：\n\n"
        "【查詢位置】：查看戴著眼鏡的家人現在在哪裡。\n"
        "【眼鏡畫面】：回傳眼鏡目前的即時視角，讓您看看他眼前的環境。\n"
        "【眼鏡狀態】：確認眼鏡的連線、目前的導航模式與最新語音指令。\n"
        "【導航回家】：遠端啟動眼鏡的導航功能，引導家人平安回家。\n"
        "【緊急求助】：發送目前位置與現場畫面（通常由眼鏡端緊急觸發）。\n\n"
        "💡 傳送「功能」或「幫助」即可再次呼叫此清單。"
    )

    if "查詢位置" in msg or "位置" in msg or "在哪" in msg:
        gps = main._get_last_gps(max_age_sec=60)
        if gps:
            map_url = f"https://www.google.com/maps?q={gps['lat']},{gps['lng']}"
            res = f"📍 馬上為您回報！家人目前的位置在這裡：\n{map_url}"
        else:
            res = "📍 目前還在努力定位中，或暫時沒有 GPS 訊號，請稍等一下再試試看喔！"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=res))

    elif "拍攝畫面" in msg or "眼鏡畫面" in msg or "看看" in msg or "環境" in msg:
        image_url = f"{NGROK_BASE_URL}/api/line_snapshot?t={int(time.time())}"
        line_bot_api.reply_message(
            event.reply_token,
            [
                TextSendMessage(text="📸 沒問題，正在為您擷取眼鏡目前的即時畫面..."),
                ImageSendMessage(original_content_url=image_url, preview_image_url=image_url),
            ],
        )

    elif "眼鏡狀態" in msg or "狀態" in msg:
        nav_session = get_nav_session()
        mode = nav_session.get_state().value
        last_voice = main._recent_voice_intents[-1]["text"] if main._recent_voice_intents else "無"

        res = (
            "👓 【設備狀態回報】\n"
            "● 連線狀態：🟢 正常運作中\n"
            f"● 目前模式：{mode}\n"
            f"● 最新語音指令：{last_voice}\n"
            "一切平安，請您放心！"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=res))

    elif "回家" in msg:
        global _home_location
        if _home_location["lat"] is None:
            res = (
                "⚠️ 您還沒有設定住家位置喔！\n"
                "請點擊 LINE 聊天室左下角的「+」，選擇「位置資訊」，搜尋並傳送您家的位置給我，就能完成設定了。"
            )
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=res))
        else:
            start_navigation_to_home(tts_enqueue, main._get_last_gps, config.LAST_GPS_MAX_AGE_SEC)
            res = (
                "🏠 已經幫您遠端啟動「導航回家」功能！\n"
                f"眼鏡現在會開始用語音引導家人，朝著「{_home_location['address']}」的方向前進囉。"
            )
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=res))

    elif "緊急求助" in msg:
        gps = main._get_last_gps(max_age_sec=60)
        sos_msg = "⚠️ 【緊急求助通知】\n使用者發出了求助訊號！\n請家屬立即確認下方位置與現場畫面。"

        messages = [TextSendMessage(text=sos_msg)]

        if gps:
            messages.append(
                LocationSendMessage(
                    title="使用者緊急位置",
                    address="點擊開啟導航",
                    latitude=gps["lat"],
                    longitude=gps["lng"],
                )
            )

        image_url = f"{NGROK_BASE_URL}/api/line_snapshot?t={int(time.time())}"
        messages.append(ImageSendMessage(original_content_url=image_url, preview_image_url=image_url))

        line_bot_api.reply_message(event.reply_token, messages)

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
