"""
IMU + GPS 融合（MVP）：
- GPS 提供絕對航向（course 或由相鄰座標估算 bearing）
- IMU gz 提供短期角速度，持續積分修正 heading
- EMA 平滑降低抖動
"""

import math
import threading
import time
from typing import Any, Dict, Optional, Tuple

import config


def _read_float_axis(
    data: Dict[str, Any],
    flat_keys: Tuple[str, ...],
    nested_name: Optional[str],
    nested_key: str,
) -> Optional[float]:
    for k in flat_keys:
        if k in data:
            try:
                return float(data[k])
            except (TypeError, ValueError):
                pass
    if nested_name:
        nested = data.get(nested_name)
        if isinstance(nested, dict) and nested_key in nested:
            try:
                return float(nested[nested_key])
            except (TypeError, ValueError):
                pass
    return None


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
        self._lock = threading.RLock()

        self._heading_deg: Optional[float] = None
        self._last_imu_ts: Optional[float] = None
        self._last_gx_dps: Optional[float] = None
        self._last_gy_dps: Optional[float] = None
        self._last_gz_dps: Optional[float] = None
        self._last_ax_g: Optional[float] = None
        self._last_ay_g: Optional[float] = None
        self._last_az_g: Optional[float] = None
        self._last_gps_ts: Optional[float] = None
        self._last_gps: Optional[Dict[str, float]] = None
        self._prev_gps: Optional[Dict[str, float]] = None
        self._last_imu_sample: Dict[str, float] = {}

        self._smooth_alpha = float(getattr(config, "HEADING_SMOOTH_ALPHA", 0.3))
        self._turn_threshold_dps = float(getattr(config, "TURN_THRESHOLD_DPS", 15.0))
        # 走停判斷（可由 config.py / env 調整）
        self._motion_acc_delta_move = float(getattr(config, "MOTION_ACC_DELTA_MOVE_G", 0.08))
        self._motion_acc_delta_stop = float(getattr(config, "MOTION_ACC_DELTA_STOP_G", 0.04))
        self._motion_gyro_move = float(getattr(config, "MOTION_GYRO_MOVE_DPS", 18.0))
        self._motion_gyro_stop = float(getattr(config, "MOTION_GYRO_STOP_DPS", 8.0))
        self._motion_hold_sec = float(getattr(config, "MOTION_HOLD_SEC", 0.35))
        self._is_moving = False
        self._motion_candidate: Optional[bool] = None
        self._motion_candidate_since = 0.0

    def update_imu(self, data: Dict[str, Any]) -> None:
        """輸入 IMU JSON；gz 用於航向積分，gx/gy/gz 與 ax/ay/az 供監控顯示。"""
        gx = _read_float_axis(data, ("gx", "gyro_x", "gyr_x"), "gyro", "x")
        gy = _read_float_axis(data, ("gy", "gyro_y", "gyr_y"), "gyro", "y")
        gz = _read_float_axis(data, ("gz", "gyro_z", "gyr_z", "z"), "gyro", "z")
        ax = _read_float_axis(data, ("ax", "acc_x"), "accel", "x")
        ay = _read_float_axis(data, ("ay", "acc_y"), "accel", "y")
        az = _read_float_axis(data, ("az", "acc_z"), "accel", "z")

        if all(v is None for v in (gx, gy, gz, ax, ay, az)):
            return

        sample: Dict[str, float] = {}
        for key, val in (("gx", gx), ("gy", gy), ("gz", gz), ("ax", ax), ("ay", ay), ("az", az)):
            if val is not None:
                sample[key] = float(val)

        now = time.time()
        with self._lock:
            updated_any = False
            if gx is not None:
                self._last_gx_dps = gx
                updated_any = True
            if gy is not None:
                self._last_gy_dps = gy
                updated_any = True
            if ax is not None:
                self._last_ax_g = ax
                updated_any = True
            if ay is not None:
                self._last_ay_g = ay
                updated_any = True
            if az is not None:
                self._last_az_g = az
                updated_any = True

            if gz is None:
                if updated_any:
                    self._update_motion_state_locked(now)
                    self._last_imu_ts = now
                    self._last_imu_sample = dict(sample)
                return

            self._last_gz_dps = gz
            self._update_motion_state_locked(now)
            self._last_imu_sample = dict(sample)
            if self._heading_deg is None:
                self._heading_deg = 0.0
                self._last_imu_ts = now
                return

            if self._last_imu_ts is not None:
                dt = max(0.0, min(now - self._last_imu_ts, 1.0))
                self._heading_deg = _normalize_deg(self._heading_deg + gz * dt)

            self._last_imu_ts = now

    def _update_motion_state_locked(self, now: float) -> None:
        ax = self._last_ax_g
        ay = self._last_ay_g
        az = self._last_az_g
        gx = self._last_gx_dps
        gy = self._last_gy_dps
        gz = self._last_gz_dps
        if None in (ax, ay, az, gx, gy, gz):
            return

        # 加速度單位假設為 g，靜止時 |a| 約 1g。
        acc_norm = math.sqrt((ax or 0.0) ** 2 + (ay or 0.0) ** 2 + (az or 0.0) ** 2)
        acc_delta = abs(acc_norm - 1.0)
        gyro_norm = math.sqrt((gx or 0.0) ** 2 + (gy or 0.0) ** 2 + (gz or 0.0) ** 2)

        if self._is_moving:
            motion_vote = not (
                acc_delta <= self._motion_acc_delta_stop and gyro_norm <= self._motion_gyro_stop
            )
        else:
            motion_vote = (
                acc_delta >= self._motion_acc_delta_move or gyro_norm >= self._motion_gyro_move
            )

        if self._motion_candidate is None or self._motion_candidate != motion_vote:
            self._motion_candidate = motion_vote
            self._motion_candidate_since = now
            return

        if (now - self._motion_candidate_since) >= self._motion_hold_sec:
            self._is_moving = bool(self._motion_candidate)

    def get_motion_state(self) -> str:
        with self._lock:
            return "moving" if self._is_moving else "stopped"

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
        if gz is None:
            return None
        if gz >= self._turn_threshold_dps:
            return "left"
        if gz <= -self._turn_threshold_dps:
            return "right"
        return None

    def get_confidence(self) -> float:
        with self._lock:
            gps_ts = self._last_gps_ts
            imu_ts = self._last_imu_ts
            gz = abs(self._last_gz_dps or 0.0)
        now = time.time()
        gps_age = 99.0 if gps_ts is None else now - gps_ts
        imu_age = 99.0 if imu_ts is None else now - imu_ts

        gps_score = 1.0 if gps_age < 2 else 0.7 if gps_age < 5 else 0.4 if gps_age < 10 else 0.1
        imu_score = 1.0 if imu_age < 1 else 0.7 if imu_age < 3 else 0.3
        motion_penalty = 0.85 if gz > 80 else 1.0
        return round(max(0.0, min(1.0, gps_score * 0.6 + imu_score * 0.4)) * motion_penalty, 2)

    def get_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            def _r(v: Optional[float]) -> Optional[float]:
                return None if v is None else round(v, 2)

            dbg = (
                {k: round(v, 2) for k, v in self._last_imu_sample.items()}
                if self._last_imu_sample
                else None
            )
            return {
                "heading_deg": self.get_heading_deg(),
                "turning": self.is_turning_left_right(),
                "confidence": self.get_confidence(),
                "gx": _r(self._last_gx_dps),
                "gy": _r(self._last_gy_dps),
                "gz": _r(self._last_gz_dps),
                "ax": _r(self._last_ax_g),
                "ay": _r(self._last_ay_g),
                "az": _r(self._last_az_g),
                "is_moving": self._is_moving,
                "motion_state": "moving" if self._is_moving else "stopped",
                "last_imu_sample": dbg,
            }


_fusion = ImuGpsFusion()


def get_fusion() -> ImuGpsFusion:
    return _fusion

