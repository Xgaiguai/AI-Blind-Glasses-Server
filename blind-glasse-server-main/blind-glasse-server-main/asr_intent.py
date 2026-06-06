"""
語音意圖辨識：
- Whisper 轉文字後由 Gemini（或關鍵字）分類意圖
- 含 NAV_HOME, STOP_NAV, SCENE_DESC, ITEM_SEARCH, ITEM_FOUND, TRAFFIC_LIGHT, DISTRESS, OTHER

DISTRESS：求救語（救命、救救我等）→ 觸發家屬 LINE 推播（需 LINE_NOTIFY_ENABLE 與 TARGET_IDS）。
ITEM_SEARCH 會額外回傳 `target`（目標物品名稱）。
"""

import json
import re
from typing import Any, Dict, Optional

from gemini_pool import call_with_pool, has_key

# 供語音緊急通報時附在 LINE 推播（僅最後一次轉寫）
_last_transcript: str = ""


def get_last_transcript() -> str:
    return _last_transcript

# 標準意圖枚舉值（與 intent_router 一致）
INTENT_NAV_HOME = "NAV_HOME"
INTENT_STOP_NAV = "STOP_NAV"
INTENT_SCENE_DESC = "SCENE_DESC"
INTENT_ITEM_SEARCH = "ITEM_SEARCH"
INTENT_ITEM_FOUND = "ITEM_FOUND"
INTENT_TRAFFIC_LIGHT = "TRAFFIC_LIGHT"
INTENT_DISTRESS = "DISTRESS"
INTENT_OTHER = "OTHER"

VOICE_INTENT_PROMPT = (
    "使用者說了一句話。請只回覆「JSON」，不要回覆任何其他文字。\n"
    "\n"
    "你只能輸出以下其中一種 JSON 結構：\n"
    "1) {\"intent\":\"NAV_HOME\"}\n"
    "2) {\"intent\":\"STOP_NAV\"}\n"
    "3) {\"intent\":\"SCENE_DESC\"}\n"
    "4) {\"intent\":\"ITEM_SEARCH\",\"target\":\"<目標物品名稱>\"}\n"
    "5) {\"intent\":\"ITEM_FOUND\"}\n"
    "6) {\"intent\":\"TRAFFIC_LIGHT\"}\n"
    "7) {\"intent\":\"DISTRESS\"}\n"
    "8) {\"intent\":\"OTHER\"}\n"
    "\n"
    "規則：\n"
    "- 若使用者表達緊急求救（例如：救命、救救我、我有危險、快救我、SOS、幫幫我、我跌倒了爬不起來、好可怕快來）→ intent=DISTRESS\n"
    "- 若使用者說「找到了/拿到了/我拿到/拿起來了/找到它了」→ 回覆 intent=ITEM_FOUND\n"
    "- 若使用者說「幫我找一下/找一下/幫我找/尋找/找物品」→ 回覆 intent=ITEM_SEARCH 並抽取後面的物品名為 target。\n"
    "- 若找物品但沒有明確說出物品名，target 請回覆空字串 \"\"。\n"
    "- 其餘依原本導航/停止/描述畫面/紅綠燈判斷。\n"
)

# 台灣版：Gemini 只看 transcript（避免音訊多模态依赖）
TEXT_INTENT_PROMPT = (
    "使用者已经提供了一段转写文字。请只回覆「JSON」，不要回覆任何其他文字。\n"
    "\n"
    "你只能输出以下其中一种 JSON 结构：\n"
    "1) {\"intent\":\"NAV_HOME\"}\n"
    "2) {\"intent\":\"STOP_NAV\"}\n"
    "3) {\"intent\":\"SCENE_DESC\"}\n"
    "4) {\"intent\":\"ITEM_SEARCH\",\"target\":\"<目標物品名稱>\"}\n"
    "5) {\"intent\":\"ITEM_FOUND\"}\n"
    "6) {\"intent\":\"TRAFFIC_LIGHT\"}\n"
    "7) {\"intent\":\"DISTRESS\"}\n"
    "8) {\"intent\":\"OTHER\"}\n"
    "\n"
    "規則：\n"
    "- 若使用者表达紧急求救（救命、救救我、有危险、快救我、SOS、帮帮我、我跌倒了起不来等）→ intent=DISTRESS\n"
    "- 若使用者说「找到了/拿到了/我拿到/拿起來了/找到它了」→ 回覆 intent=ITEM_FOUND\n"
    "- 若使用者说「幫我找一下/找一下/幫我找/尋找/找物品」→ 回覆 intent=ITEM_SEARCH 並抽取後面的物品名為 target。\n"
    "- 若找物品但没有明確說出物品名，target 請回覆空字串 \"\"。\n"
    "- 其餘依原本導航/停止/描述畫面/紅綠燈判斷。\n"
)


def _ensure_configured() -> bool:
    return has_key()


def _keyword_fallback(text: str) -> str:
    """關鍵字 fallback：模型輸出異常時仍可分類。"""
    t = (text or "").strip().lower()
    distress = (
        "救命" in t
        or "救救我" in t
        or "救救" in t
        or "有危險" in t
        or "快救我" in t
        or t.strip() == "sos"
        or "幫幫我" in t
        or "快來救" in t
        or "需要幫助" in t
        or "救救我" in t
        or "我跌倒了" in t
        or "爬不起來" in t
        or "好可怕" in t
        or "快來人" in t
    )
    if distress:
        return INTENT_DISTRESS
    if "導航到家" in t or ("導航" in t and "家" in t) or "帶我回家" in t:
        return INTENT_NAV_HOME
    if ("停止" in t and "導航" in t) or "結束導航" in t or "取消導航" in t:
        return INTENT_STOP_NAV
    if "找到了" in t or "拿到了" in t or "找到了" in t or "拿到" in t:
        return INTENT_ITEM_FOUND
    if "描述" in t or "看看" in t or "這是什麼" in t or "幫我看" in t:
        return INTENT_SCENE_DESC
    if "找" in t and ("物" in t or "東西" in t) or "幫我找" in t:
        return INTENT_ITEM_SEARCH
    if "紅綠燈" in t or "紅燈" in t or "綠燈" in t:
        return INTENT_TRAFFIC_LIGHT
    return INTENT_OTHER


def _extract_item_target(text: str) -> str:
    """
    簡單擷取「找物品」語句中的物品名（fallback 用）。
    例：幫我找一下紅牛 -> 紅牛
    """
    if not text:
        return ""
    t = text.strip()
    # 優先匹配：找一下/找物品/幫我找 ... 後面到句末或常見標點
    m = re.search(r"(?:幫我)?\s*找(?:一下|物品|到)?\s*([^\s，。！？!?、]+)", t)
    if m:
        return m.group(1).strip()
    # 次要：尋找/找尋 後面
    m = re.search(r"(?:尋找)\s*([^\s，。！？!?、]+)", t)
    if m:
        return m.group(1).strip()
    return ""


def _try_parse_json(raw: str) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    s = raw.strip()
    # 允許模型前後夾雜文字：嘗試截出 JSON 區塊
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        s = s[start : end + 1]
    try:
        obj = json.loads(s)
        if isinstance(obj, dict) and "intent" in obj:
            return obj
    except Exception:
        return None
    return None


def _get_intent_from_text(transcript: str) -> Dict[str, Optional[str]]:
    """
    從 transcript 文本抽取意圖：
    - Gemini 可用：走 Gemini（只回 JSON）
    - 不可用：keyword fallback + target 抽取
    """
    t = (transcript or "").strip()
    if not t:
        return {"intent": INTENT_OTHER, "target": None}

    if not _ensure_configured():
        intent = _keyword_fallback(t)
        if intent == INTENT_ITEM_SEARCH:
            return {"intent": INTENT_ITEM_SEARCH, "target": _extract_item_target(t)}
        if intent == INTENT_ITEM_FOUND:
            return {"intent": INTENT_ITEM_FOUND, "target": None}
        return {"intent": intent, "target": None}

    try:
        response = call_with_pool(lambda model: model.generate_content([TEXT_INTENT_PROMPT, t]))
        raw = (getattr(response, "text", "") or "").strip()

        parsed = _try_parse_json(raw)
        if parsed is None:
            intent = _keyword_fallback(t)
            if intent == INTENT_ITEM_SEARCH:
                return {"intent": INTENT_ITEM_SEARCH, "target": _extract_item_target(t)}
            if intent == INTENT_ITEM_FOUND:
                return {"intent": INTENT_ITEM_FOUND, "target": None}
            return {"intent": intent, "target": None}

        intent = str(parsed.get("intent") or INTENT_OTHER)
        target = parsed.get("target")

        if intent == INTENT_ITEM_SEARCH:
            extracted = _extract_item_target(t)
            return {"intent": INTENT_ITEM_SEARCH, "target": str(target or extracted or "").strip()}
        if intent == INTENT_ITEM_FOUND:
            return {"intent": INTENT_ITEM_FOUND, "target": None}

        if intent in {
            INTENT_NAV_HOME,
            INTENT_STOP_NAV,
            INTENT_SCENE_DESC,
            INTENT_TRAFFIC_LIGHT,
            INTENT_DISTRESS,
            INTENT_OTHER,
        }:
            return {"intent": intent, "target": None}

        return {"intent": INTENT_OTHER, "target": None}
    except Exception:
        intent = _keyword_fallback(t)
        if intent == INTENT_ITEM_SEARCH:
            return {"intent": INTENT_ITEM_SEARCH, "target": _extract_item_target(t)}
        if intent == INTENT_ITEM_FOUND:
            return {"intent": INTENT_ITEM_FOUND, "target": None}
        return {"intent": intent, "target": None}


def get_voice_intent(audio_wav_bytes: bytes) -> Dict[str, Optional[str]]:
    """
    使用本地 Whisper 转文字（transcript），再用 text intent 抽取意图。

    回傳 dict：
    - {"intent": "<INTENT>", "target": "<目標物品名或空字串/None>"}
    """
    try:
        if not audio_wav_bytes:
            return {"intent": INTENT_OTHER, "target": None}

        from local_whisper_asr import transcribe_wav_bytes

        global _last_transcript
        transcript = transcribe_wav_bytes(audio_wav_bytes)
        _last_transcript = (transcript or "").strip()
        return _get_intent_from_text(transcript)
    except Exception as e:
        print(f"[ASR intent] Error (whisper): {e}")
        return {"intent": INTENT_OTHER, "target": None}
