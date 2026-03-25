"""
語音意圖辨識：將 WAV 送交 Gemini，回傳標準意圖枚舉（NAV_HOME, STOP_NAV, SCENE_DESC, ITEM_SEARCH, TRAFFIC_LIGHT, OTHER）。
"""

import base64
from typing import Optional

import config

try:
    import google.generativeai as genai  # type: ignore[import-untyped]
    _HAS_GEMINI = True
except ImportError:
    _HAS_GEMINI = False

# 標準意圖枚舉值（與 intent_router 一致）
INTENT_NAV_HOME = "NAV_HOME"
INTENT_STOP_NAV = "STOP_NAV"
INTENT_SCENE_DESC = "SCENE_DESC"
INTENT_ITEM_SEARCH = "ITEM_SEARCH"
INTENT_TRAFFIC_LIGHT = "TRAFFIC_LIGHT"
INTENT_OTHER = "OTHER"

VOICE_INTENT_PROMPT = (
    "使用者說了一句話。請只回覆以下其中一項，不要其他說明：\n"
    "- 若內容是要求導航回家或帶我回家，回覆「導航到家」\n"
    "- 若內容是停止導航、結束導航、取消導航，回覆「停止導航」\n"
    "- 若內容是描述畫面、看看什麼、這是什麼、幫我看，回覆「描述畫面」\n"
    "- 若內容是找物品、幫我找、找一下，回覆「找物品」\n"
    "- 若內容是紅綠燈、看紅綠燈、檢測紅綠燈，回覆「紅綠燈」\n"
    "- 否則回覆「其他」"
)


def _ensure_configured() -> bool:
    if not getattr(config, "GEMINI_API_KEY", ""):
        return False
    if _HAS_GEMINI:
        genai.configure(api_key=config.GEMINI_API_KEY)  # type: ignore[attr-defined]
    return _HAS_GEMINI


def _keyword_fallback(text: str) -> str:
    """關鍵字 fallback：模型輸出異常時仍可分類。"""
    t = (text or "").strip().lower()
    if "導航到家" in t or ("導航" in t and "家" in t) or "帶我回家" in t:
        return INTENT_NAV_HOME
    if ("停止" in t and "導航" in t) or "結束導航" in t or "取消導航" in t:
        return INTENT_STOP_NAV
    if "描述" in t or "看看" in t or "這是什麼" in t or "幫我看" in t:
        return INTENT_SCENE_DESC
    if "找" in t and ("物" in t or "東西" in t) or "幫我找" in t:
        return INTENT_ITEM_SEARCH
    if "紅綠燈" in t or "紅燈" in t or "綠燈" in t:
        return INTENT_TRAFFIC_LIGHT
    return INTENT_OTHER


def get_voice_intent(audio_wav_bytes: bytes) -> str:
    """
    將 WAV 送給 Gemini，辨識意圖。回傳標準意圖枚舉。
    """
    if not audio_wav_bytes:
        return INTENT_OTHER

    if not _ensure_configured():
        return INTENT_OTHER

    try:
        model = genai.GenerativeModel(getattr(config, "GEMINI_MODEL", "gemini-2.5-flash"))  # type: ignore[attr-defined]
        audio_part = {
            "inline_data": {
                "mime_type": "audio/wav",
                "data": base64.standard_b64encode(audio_wav_bytes).decode("ascii"),
            }
        }
        response = model.generate_content([VOICE_INTENT_PROMPT, audio_part])
        if not response or not response.text:
            return INTENT_OTHER
        raw = response.text.strip()
        # 正規化為標準意圖
        fallback = _keyword_fallback(raw)
        if fallback != INTENT_OTHER:
            return fallback
        if "導航到家" in raw or ("導航" in raw and "家" in raw):
            return INTENT_NAV_HOME
        if "停止導航" in raw or "結束導航" in raw or "取消導航" in raw:
            return INTENT_STOP_NAV
        if "描述畫面" in raw or "看看" in raw or "這是什麼" in raw:
            return INTENT_SCENE_DESC
        if "找物品" in raw or "找" in raw and "物" in raw:
            return INTENT_ITEM_SEARCH
        if "紅綠燈" in raw:
            return INTENT_TRAFFIC_LIGHT
        return INTENT_OTHER
    except Exception as e:
        print(f"[ASR intent] Error: {e}")
    return INTENT_OTHER
