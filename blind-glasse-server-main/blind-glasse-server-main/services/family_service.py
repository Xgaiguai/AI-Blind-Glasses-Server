"""
家屬通知服務：統一管理 LINE 推播、緊急通知策略。
從 main.py 抽離，降低耦合。
"""

from __future__ import annotations

import time
import threading
from typing import Any, Dict, Optional

from event_engine import EventEngine
from line_notifier import LineNotifier


class FamilyService:
    def __init__(self, event_engine: EventEngine, notifier: LineNotifier) -> None:
        self._engine = event_engine
        self._notifier = notifier
        self._lock = threading.Lock()

    def notify_text(self, text: str) -> bool:
        try:
            result = self._notifier.push_text(text)
            return bool(result.get("ok"))
        except Exception:
            return False

    def notify_location(self) -> bool:
        gps = self._engine.get_snapshot().get("last_gps") or {}
        lat = gps.get("lat")
        lng = gps.get("lng")
        if lat is None or lng is None:
            return False
        try:
            self._notifier.push_location(
                title="眼鏡目前位置",
                address=gps.get("map_url") or "Google Maps",
                lat=float(lat),
                lng=float(lng),
            )
            return True
        except Exception:
            return False

    def emergency(self, source: str, extra_text: str = "") -> Dict[str, Any]:
        ev = self._engine.emergency_event(source)
        if self._engine.should_send_line():
            msg = extra_text or str(ev.get("text") or "緊急通知")
            self.notify_text(msg)
            self.notify_location()
        return ev

    def build_status_text(self, health_snapshot: Dict[str, Any]) -> str:
        snap = self._engine.get_snapshot()
        gps = snap.get("last_gps") or {}
        fall = snap.get("fall") or {}
        return (
            f"伺服器狀態\n"
            f"- Uptime: {health_snapshot.get('uptime_sec')}s\n"
            f"- IMU age: {health_snapshot.get('last_imu_age_sec')}\n"
            f"- GPS age: {health_snapshot.get('last_gps_age_sec')}\n"
            f"- 跌倒警示: {'ALERT' if fall.get('active') else 'normal'}\n"
            f"- GPS: {gps.get('lat')}, {gps.get('lng')}"
        )

    def build_location_text(self) -> str:
        gps = (self._engine.get_snapshot().get("last_gps") or {})
        lat = gps.get("lat")
        lng = gps.get("lng")
        map_url = gps.get("map_url") or ""
        if lat is None or lng is None:
            return "目前尚未收到 GPS 定位資料。"
        return f"眼鏡目前位置：{lat}, {lng}\n地圖：{map_url}"

    @property
    def is_ready(self) -> bool:
        return self._notifier.is_ready()
