"""
LINE 家屬對話：純文字 Gemini 回覆（不帶影像），依伺服器摘要回答自然語言。
"""

from __future__ import annotations

from gemini_pool import call_with_pool, has_key


def family_line_reply(user_message: str, context_block: str) -> str:
    """
    家屬在 LINE 傳任意文字時，由 Gemini 依 context 簡短回覆（繁中）。
    無 key 或失敗時回空字串，由呼叫端 fallback。
    """
    msg = (user_message or "").strip()
    ctx = (context_block or "").strip()
    if not msg or not has_key():
        return ""

    system = (
        "你是「AI 導盲眼鏡」官方帳號的助理，協助視障者的家屬了解安全與裝置狀態。\n"
        "規則：\n"
        "- 只用繁體中文，口語、簡短，最多約 150 字。\n"
        "- 下面「系統摘要」是唯一事實來源；不要編造座標、時間或感測數據。\n"
        "- 若摘要沒有 GPS，就說目前尚無定位資料，可請使用者確認眼鏡已開機並在戶外。\n"
        "- 可溫和閒聊（例如問候），但仍可順便提醒可查「位置」「狀態」快捷指令。\n"
        "- 不要輸出 JSON、不要條列過長。\n"
    )
    prompt = f"{system}\n【系統摘要】\n{ctx}\n\n【家屬訊息】\n{msg}"

    try:
        response = call_with_pool(lambda model: model.generate_content([prompt]))
        out = (getattr(response, "text", "") or "").strip()
        if len(out) > 500:
            out = out[:497] + "…"
        return out
    except Exception as e:
        print(f"[LINE Gemini] {e}")
        return ""
