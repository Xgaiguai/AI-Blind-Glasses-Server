from __future__ import annotations

import time
from typing import Any, Dict, Optional

import config
from fall_detector import FallDetector


def _map_url(lat: Optional[float], lng: Optional[float]) -> str:
    if lat is None or lng is None:
        return ""
    return f"https://maps.google.com/?q={lat},{lng}"


class EventEngine:
    def __init__(self) -> None:
        self.fall = FallDetector()
        self._last_gps: Optional[Dict[str, Any]] = None
        self._last_imu: Optional[Dict[str, Any]] = None
        self._last_event: Optional[Dict[str, Any]] = None
        self._line_cooldown = float(getattr(config, "LINE_NOTIFY_COOLDOWN_SEC", 90))
        self._last_line_notify_ts = 0.0
        self._line_notify_enabled = bool(getattr(config, "LINE_NOTIFY_ENABLE", False))

    def update_gps(self, data: Dict[str, Any]) -> None:
        now = time.time()
        lat = data.get("lat")
        lng = data.get("lng")
        try:
            lat = float(lat) if lat is not None else None
            lng = float(lng) if lng is not None else None
        except Exception:
            lat, lng = None, None
        self._last_gps = {
            "lat": lat,
            "lng": lng,
            "course": data.get("course"),
            "sat": data.get("sat"),
            "ts": now,
            "map_url": _map_url(lat, lng),
        }

    def update_imu(self, data: Dict[str, Any]) -> Dict[str, Any]:
        now = time.time()
        self._last_imu = {"raw": data, "ts": now}
        fall_state = self.fall.update(data)
        notify_event: Optional[Dict[str, Any]] = None
        if bool(getattr(config, "FALL_ENABLE", True)) and fall_state.get("triggered"):
            notify_event = {
                "type": "fall_alert",
                "text": "警示：偵測到疑似跌倒，請盡快確認眼鏡使用者狀況。",
                "payload": {
                    "fall": fall_state,
                    "gps": self._last_gps,
                },
            }
            self._last_event = {"ts": now, **notify_event}
        return {"fall": fall_state, "notify_event": notify_event}

    def emergency_event(self, note: str = "") -> Dict[str, Any]:
        now = time.time()
        event = {
            "type": "emergency",
            "text": "緊急通知：眼鏡端觸發緊急求助。",
            "payload": {"note": note, "gps": self._last_gps},
            "ts": now,
        }
        self._last_event = event
        return event

    def should_send_line(self) -> bool:
        if not self._line_notify_enabled:
            return False
        now = time.time()
        if (now - self._last_line_notify_ts) < self._line_cooldown:
            return False
        self._last_line_notify_ts = now
        return True

    def get_snapshot(self) -> Dict[str, Any]:
        return {
            "last_gps": self._last_gps,
            "last_imu_ts": (self._last_imu or {}).get("ts"),
            "last_event": self._last_event,
            "fall": {
                "active": self.fall._active,  # monitor 用
                "last_alert_ts": self.fall._last_alert,
            },
            "line_notify_enable": self._line_notify_enabled,
        }

