from __future__ import annotations

import time
from collections import deque
from typing import Any, Deque, Dict, Optional, Tuple


class LatencyTracker:
    """Records per-stage timestamps for end-to-end latency measurement."""

    def __init__(self, max_records: int = 50) -> None:
        self._records: Deque[Dict[str, Any]] = deque(maxlen=max_records)
        self._pending: Dict[str, Dict[str, float]] = {}

    def begin(self, request_id: str, stage: str = "arrive") -> None:
        self._pending[request_id] = {stage: time.time()}

    def mark(self, request_id: str, stage: str) -> None:
        rec = self._pending.get(request_id)
        if rec is not None:
            rec[stage] = time.time()

    def finish(self, request_id: str, stage: str = "done") -> Optional[Dict[str, Any]]:
        rec = self._pending.pop(request_id, None)
        if rec is None:
            return None
        rec[stage] = time.time()
        first_ts = min(rec.values())
        summary = {k: round((v - first_ts) * 1000, 1) for k, v in rec.items()}
        summary["total_ms"] = round((rec[stage] - first_ts) * 1000, 1)
        summary["id"] = request_id
        summary["ts"] = first_ts
        self._records.append(summary)
        return summary

    def recent(self, n: int = 10) -> list:
        return list(self._records)[-n:]

    def stats(self) -> Dict[str, Any]:
        if not self._records:
            return {"count": 0}
        totals = [r["total_ms"] for r in self._records if "total_ms" in r]
        if not totals:
            return {"count": 0}
        totals_sorted = sorted(totals)
        p50 = totals_sorted[len(totals_sorted) // 2]
        p95 = totals_sorted[min(len(totals_sorted) - 1, int(len(totals_sorted) * 0.95))]
        return {
            "count": len(totals_sorted),
            "p50_ms": round(p50, 1),
            "p95_ms": round(p95, 1),
            "max_ms": round(totals_sorted[-1], 1),
            "min_ms": round(totals_sorted[0], 1),
        }


class ServerHealth:
    def __init__(self) -> None:
        self.started_ts = time.time()
        self.last_imu_ts = 0.0
        self.last_gps_ts = 0.0
        self.last_error = ""
        self.latency = LatencyTracker()

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
            "latency_stats": self.latency.stats(),
        }

