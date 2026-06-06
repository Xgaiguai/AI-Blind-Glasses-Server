from __future__ import annotations

import time
from typing import Any, Dict

import config


class FallDetector:
    """
    簡化跌倒偵測：
    - |gz| 超過門檻後，持續 confirm_sec 視為疑似跌倒
    - 觸發後有 cooldown，避免重複告警
    """

    def __init__(self) -> None:
        self.threshold = float(getattr(config, "FALL_GZ_DPS_THRESHOLD", 160.0))
        self.confirm_sec = float(getattr(config, "FALL_CONFIRM_SEC", 1.2))
        self.cooldown_sec = float(getattr(config, "FALL_COOLDOWN_SEC", 120.0))
        self._hit_since = 0.0
        self._last_alert = 0.0
        self._active = False

    def _extract_gz(self, data: Dict[str, Any]) -> float:
        gz = None
        for k in ("gz", "gyro_z", "gyr_z", "z"):
            if k in data:
                gz = data.get(k)
                break
        if gz is None and isinstance(data.get("gyro"), dict):
            gz = data["gyro"].get("z")
        return float(gz) if gz is not None else 0.0

    def update(self, data: Dict[str, Any]) -> Dict[str, Any]:
        now = time.time()
        try:
            gz = self._extract_gz(data)
        except Exception:
            gz = 0.0
        hit = abs(gz) >= self.threshold

        if hit:
            if self._hit_since <= 0:
                self._hit_since = now
        else:
            self._hit_since = 0.0
            self._active = False

        triggered = False
        if self._hit_since > 0 and (now - self._hit_since) >= self.confirm_sec:
            if (now - self._last_alert) >= self.cooldown_sec:
                self._last_alert = now
                self._active = True
                triggered = True

        return {
            "gz_dps": round(gz, 2),
            "hit_threshold": hit,
            "active": self._active,
            "triggered": triggered,
            "last_alert_ts": self._last_alert,
        }

