from __future__ import annotations

import time
from typing import Any, Dict


class ServerHealth:
    def __init__(self) -> None:
        self.started_ts = time.time()
        self.last_imu_ts = 0.0
        self.last_gps_ts = 0.0
        self.last_error = ""

    def touch_imu(self) -> None:
        self.last_imu_ts = time.time()

    def touch_gps(self) -> None:
        self.last_gps_ts = time.time()

    def set_error(self, msg: str) -> None:
        self.last_error = str(msg or "")

    def snapshot(self) -> Dict[str, Any]:
        now = time.time()
        return {
            "uptime_sec": round(now - self.started_ts, 1),
            "last_imu_age_sec": round(now - self.last_imu_ts, 1) if self.last_imu_ts > 0 else None,
            "last_gps_age_sec": round(now - self.last_gps_ts, 1) if self.last_gps_ts > 0 else None,
            "last_error": self.last_error,
        }

