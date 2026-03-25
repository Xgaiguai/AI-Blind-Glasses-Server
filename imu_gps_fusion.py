"""
IMU + GPS 融合（MVP）：
- GPS 提供絕對航向（course 或由相鄰座標估算 bearing）
- IMU gz 提供短期角速度，持續積分修正 heading
- EMA 平滑降低抖動
"""

import math
import threading
import time
from typing import Any, Dict, Optional

import config


def _normalize_deg(deg: float) -> float:
    out = deg % 360.0
    if out < 0:
        out += 360.0
    return out


def _shortest_delta_deg(a: float, b: float) -> float:
    """
    回傳從 a 轉到 b 的最短角差（-180, 180]。
    """
    d = (b - a + 180.0) % 360.0 - 180.0
    return d


def _bearing_deg(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """兩點方位角（0~360）。"""
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dl = math.radians(lng2 - lng1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return _normalize_deg(math.degrees(math.atan2(y, x)))


class ImuGpsFusion:
    def __init__(self) -> None:
        self._lock = threading.Lock()

        self._heading_deg: Optional[float] = None
        self._last_imu_ts: Optional[float] = None
        self._last_gz_dps: float = 0.0
        self._last_gps_ts: Optional[float] = None
        self._last_gps: Optional[Dict[str, float]] = None
        self._prev_gps: Optional[Dict[str, float]] = None

        self._smooth_alpha = float(getattr(config, "HEADING_SMOOTH_ALPHA", 0.3))
        self._turn_threshold_dps = float(getattr(config, "TURN_THRESHOLD_DPS", 15.0))

    def update_imu(self, data: Dict[str, Any]) -> None:
        """輸入 IMU JSON，重點使用 gz（deg/s）。"""
        gz = None
        for k in ("gz", "gyro_z", "gyr_z", "z"):
            if k in data:
                gz = data.get(k)
                break
        if gz is None and isinstance(data.get("gyro"), dict):
            gz = data["gyro"].get("z")
        if gz is None:
            return

        try:
            gz_dps = float(gz)
        except (TypeError, ValueError):
            return

        now = time.time()
        with self._lock:
            if self._heading_deg is None:
                self._heading_deg = 0.0
                self._last_imu_ts = now
                self._last_gz_dps = gz_dps
                return

            if self._last_imu_ts is not None:
                dt = max(0.0, min(now - self._last_imu_ts, 1.0))
                self._heading_deg = _normalize_deg(self._heading_deg + gz_dps * dt)

            self._last_imu_ts = now
            self._last_gz_dps = gz_dps

    def update_gps(self, lat: float, lng: float, course: Optional[float] = None) -> None:
        """輸入 GPS；course 若不存在，改由前後兩點估算。"""
        now = time.time()
        try:
            latf = float(lat)
            lngf = float(lng)
        except (TypeError, ValueError):
            return

        with self._lock:
            self._prev_gps = self._last_gps
            self._last_gps = {"lat": latf, "lng": lngf}
            self._last_gps_ts = now

            gps_heading: Optional[float] = None
            if course is not None:
                try:
                    gps_heading = _normalize_deg(float(course))
                except (TypeError, ValueError):
                    gps_heading = None
            if gps_heading is None and self._prev_gps is not None:
                gps_heading = _bearing_deg(
                    self._prev_gps["lat"],
                    self._prev_gps["lng"],
                    latf,
                    lngf,
                )

            if gps_heading is None:
                return

            if self._heading_deg is None:
                self._heading_deg = gps_heading
                return

            # 圓周角 EMA：先算最短角差，再做比例修正
            delta = _shortest_delta_deg(self._heading_deg, gps_heading)
            self._heading_deg = _normalize_deg(self._heading_deg + self._smooth_alpha * delta)

    def get_heading_deg(self) -> Optional[float]:
        with self._lock:
            if self._heading_deg is None:
                return None
            return round(self._heading_deg, 2)

    def is_turning_left_right(self) -> Optional[str]:
        with self._lock:
            gz = self._last_gz_dps
        if gz >= self._turn_threshold_dps:
            return "left"
        if gz <= -self._turn_threshold_dps:
            return "right"
        return None

    def get_confidence(self) -> float:
        with self._lock:
            gps_ts = self._last_gps_ts
            imu_ts = self._last_imu_ts
            gz = abs(self._last_gz_dps)
        now = time.time()
        gps_age = 99.0 if gps_ts is None else now - gps_ts
        imu_age = 99.0 if imu_ts is None else now - imu_ts

        gps_score = 1.0 if gps_age < 2 else 0.7 if gps_age < 5 else 0.4 if gps_age < 10 else 0.1
        imu_score = 1.0 if imu_age < 1 else 0.7 if imu_age < 3 else 0.3
        motion_penalty = 0.85 if gz > 80 else 1.0
        return round(max(0.0, min(1.0, gps_score * 0.6 + imu_score * 0.4)) * motion_penalty, 2)

    def get_snapshot(self) -> Dict[str, Any]:
        return {
            "heading_deg": self.get_heading_deg(),
            "turning": self.is_turning_left_right(),
            "confidence": self.get_confidence(),
        }


_fusion = ImuGpsFusion()


def get_fusion() -> ImuGpsFusion:
    return _fusion

