"""
Gemini API 場景分析：上傳影像與 prompt，回傳簡短描述文字。
"""

import io
from typing import Optional

import config
from gemini_pool import call_with_pool, has_key

try:
    import google.generativeai as genai  # type: ignore[import-untyped]
    _HAS_GEMINI = True
except ImportError:
    _HAS_GEMINI = False

try:
    from PIL import Image  # type: ignore[import-untyped]
    _HAS_PIL = True
except ImportError:
    Image = None  # type: ignore[assignment]
    _HAS_PIL = False


def _ensure_configured() -> bool:
    return has_key() and _HAS_GEMINI


def _call_gemini(image_bytes: bytes, prompt: str) -> str:
    """共用的 Gemini 呼叫邏輯。"""
    if not _ensure_configured():
        return ""
    try:
        def _do(model):
            if _HAS_PIL and Image is not None:
                img = Image.open(io.BytesIO(image_bytes))
                return model.generate_content([prompt, img])
            img_part = {
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": image_bytes,
                }
            }
            return model.generate_content([prompt, img_part])

        response = call_with_pool(_do)
        if response and getattr(response, "text", None):
            return str(response.text).strip()
    except Exception as e:
        print(f"[Gemini] Error: {e}")
    return ""


def analyze_scene(image_bytes: bytes, extra_prompt: str = "") -> str:
    """
    將 JPEG 影像與 prompt 送交 Gemini，回傳場景描述。
    若未設定 API key 或失敗，回傳預設提示文字。
    """
    base_prompt = getattr(config, "GEMINI_SCENE_PROMPT", "") or ""
    prompt = base_prompt
    if extra_prompt:
        prompt = f"{base_prompt}\n{extra_prompt}" if base_prompt else extra_prompt
    text = _call_gemini(image_bytes, prompt)
    if not text:
        return "場景辨識暫不可用，請稍後再試。"
    return text


def analyze_traffic_light(image_bytes: bytes) -> str:
    """
    紅綠燈專用分析：使用 GEMINI_TRAFFIC_PROMPT，只回傳模型文字。
    解析顏色請在呼叫端處理。
    """
    prompt = getattr(config, "GEMINI_TRAFFIC_PROMPT", "") or "請判斷畫面中的紅綠燈狀態。"
    text = _call_gemini(image_bytes, prompt)
    if not text:
        return "無法判斷"
    return text
