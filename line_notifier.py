from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests  # type: ignore[import-untyped]

import config


def family_quick_reply_dict() -> Dict[str, Any]:
    """家屬常用指令：LINE Quick Reply（無需上傳圖檔）。"""
    return {
        "items": [
            {
                "type": "action",
                "action": {"type": "message", "label": "位置", "text": "位置"},
            },
            {
                "type": "action",
                "action": {"type": "message", "label": "狀態", "text": "狀態"},
            },
            {
                "type": "action",
                "action": {"type": "message", "label": "緊急通報", "text": "緊急"},
            },
        ]
    }


class LineNotifier:
    PUSH_API = "https://api.line.me/v2/bot/message/push"
    REPLY_API = "https://api.line.me/v2/bot/message/reply"

    def __init__(self) -> None:
        self.token = (getattr(config, "LINE_CHANNEL_ACCESS_TOKEN", "") or "").strip()
        raw_targets = (getattr(config, "LINE_TARGET_IDS", "") or "").strip()
        self.targets = [x.strip() for x in raw_targets.split(",") if x.strip()]
        self.timeout = float(getattr(config, "LINE_REQUEST_TIMEOUT_SEC", 6.0))
        self.enabled = bool(getattr(config, "LINE_NOTIFY_ENABLE", False))

    def is_ready(self) -> bool:
        return self.enabled and bool(self.token) and len(self.targets) > 0

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def push_text(self, text: str) -> Dict[str, Any]:
        if not self.is_ready():
            return {"ok": False, "reason": "line_not_ready"}
        ok_count = 0
        errors: List[str] = []
        for to in self.targets:
            payload = {
                "to": to,
                "messages": [{"type": "text", "text": text}],
            }
            try:
                r = requests.post(self.PUSH_API, headers=self._headers(), json=payload, timeout=self.timeout)
                if 200 <= r.status_code < 300:
                    ok_count += 1
                else:
                    errors.append(f"{to}:{r.status_code}")
            except Exception as e:
                errors.append(f"{to}:{e}")
        return {"ok": ok_count > 0, "sent": ok_count, "errors": errors}

    def push_location(self, title: str, address: str, lat: float, lng: float) -> Dict[str, Any]:
        if not self.is_ready():
            return {"ok": False, "reason": "line_not_ready"}
        ok_count = 0
        errors: List[str] = []
        for to in self.targets:
            payload = {
                "to": to,
                "messages": [{
                    "type": "location",
                    "title": title,
                    "address": address,
                    "latitude": float(lat),
                    "longitude": float(lng),
                }],
            }
            try:
                r = requests.post(self.PUSH_API, headers=self._headers(), json=payload, timeout=self.timeout)
                if 200 <= r.status_code < 300:
                    ok_count += 1
                else:
                    errors.append(f"{to}:{r.status_code}")
            except Exception as e:
                errors.append(f"{to}:{e}")
        return {"ok": ok_count > 0, "sent": ok_count, "errors": errors}

    def reply_text(
        self,
        reply_token: str,
        text: str,
        quick_reply: bool = True,
        quick_reply_items: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        # reply 僅需 token；LINE_NOTIFY_ENABLE 只約束主動 push，避免關閉推播時連關鍵字回覆也失效
        if not self.token:
            return {"ok": False, "reason": "missing_token"}
        msg: Dict[str, Any] = {"type": "text", "text": text}
        if quick_reply:
            qr = quick_reply_items if quick_reply_items is not None else family_quick_reply_dict()
            msg["quickReply"] = qr
        payload = {
            "replyToken": reply_token,
            "messages": [msg],
        }
        try:
            r = requests.post(self.REPLY_API, headers=self._headers(), json=payload, timeout=self.timeout)
            return {"ok": 200 <= r.status_code < 300, "status": r.status_code}
        except Exception as e:
            return {"ok": False, "error": str(e)}

