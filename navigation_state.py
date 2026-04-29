"""
導航狀態機與共享 session 狀態模型。

本專案狀態以你現有邏輯為主，同時擴充對齊上游的「視覺模式」狀態名稱。
"""

import enum
import threading
import time
from typing import Any, Dict, List, Optional, Tuple


class NavState(enum.Enum):
    IDLE = "idle"
    NAVIGATING = "navigating"
    REROUTING = "rerouting"
    ARRIVED = "arrived"
    CROSSING_WAIT = "crossing_wait"
    CROSSING_GO = "crossing_go"

    # 以下為對齊上游架構的擴充狀態（現階段用於監控顯示/模式切換）
    BLINDPATH_NAV = "blindpath_nav"
    SEEKING_CROSSWALK = "seeking_crosswalk"
    WAIT_TRAFFIC_LIGHT = "wait_traffic_light"
    CROSSING = "crossing"
    ITEM_SEARCH = "item_search"


# 導航 step: (instruction, distance_m)
StepTuple = Tuple[str, float]

# 監控用事件: (ts, event_type, payload)
EventTuple = Tuple[float, str, Any]


class NavigationSession:
    """Thread-safe 導航 session 狀態。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()  # RLock 支援同一線程重入，get_snapshot 內呼叫 get_next_step_for_display 不 deadlock
        self._state = NavState.IDLE
        self._steps: List[StepTuple] = []
        self._current_step_index = 0
        self._last_reroute_ts = 0.0
        self._last_tts_text = ""
        self._step_start_dist_to_home: Optional[float] = None  # 當前 step 開始時的 dist_to_home
        self._events: List[EventTuple] = []
        self._max_events = 50

    def get_state(self) -> NavState:
        with self._lock:
            return self._state

    def set_state(self, state: NavState) -> None:
        with self._lock:
            self._state = state
            self._emit_event("state_change", {"state": state.value})

    def get_steps(self) -> List[StepTuple]:
        with self._lock:
            return list(self._steps)

    def set_steps(self, steps: List[StepTuple], dist_to_home: Optional[float] = None) -> None:
        with self._lock:
            self._steps = steps
            self._current_step_index = 0
            self._step_start_dist_to_home = dist_to_home
            self._emit_event("route_updated", {"step_count": len(steps)})

    def get_current_step_index(self) -> int:
        with self._lock:
            return self._current_step_index

    def advance_step(self, dist_to_home: Optional[float] = None) -> bool:
        """推進到下一步；若已無步則回傳 False。"""
        with self._lock:
            if self._current_step_index >= len(self._steps) - 1:
                return False
            self._current_step_index += 1
            self._step_start_dist_to_home = dist_to_home
            self._emit_event("step_advanced", {"index": self._current_step_index})
            return True

    def get_next_step(self) -> Optional[StepTuple]:
        """取得當前應執行的 step（含距離）。"""
        with self._lock:
            if not self._steps or self._current_step_index >= len(self._steps):
                return None
            return self._steps[self._current_step_index]

    def get_next_step_for_display(self) -> Optional[Dict[str, Any]]:
        """供監控顯示用：instruction, distance_m, index, total"""
        with self._lock:
            if not self._steps or self._current_step_index >= len(self._steps):
                return None
            step = self._steps[self._current_step_index]
            return {
                "instruction": step[0],
                "distance_m": step[1],
                "index": self._current_step_index,
                "total": len(self._steps),
            }

    def clear_route(self) -> None:
        with self._lock:
            self._steps = []
            self._current_step_index = 0

    def can_reroute(self, min_interval_sec: float) -> bool:
        with self._lock:
            return (time.time() - self._last_reroute_ts) >= min_interval_sec

    def mark_reroute(self) -> None:
        with self._lock:
            self._last_reroute_ts = time.time()

    def set_last_tts(self, text: str) -> None:
        with self._lock:
            self._last_tts_text = text

    def get_last_tts(self) -> str:
        with self._lock:
            return self._last_tts_text

    def _emit_event(self, event_type: str, payload: Any) -> None:
        ev = (time.time(), event_type, payload)
        self._events.append(ev)
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events:]

    def get_recent_events(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            out = []
            for ts, evt, payload in self._events[-limit:]:
                out.append({"ts": ts, "type": evt, "payload": payload})
            return out

    def get_step_start_dist(self) -> Optional[float]:
        with self._lock:
            return self._step_start_dist_to_home

    def set_step_start_dist(self, dist: Optional[float]) -> None:
        with self._lock:
            self._step_start_dist_to_home = dist

    def get_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "state": self._state.value,
                "last_tts": self._last_tts_text,
                "next_step": self.get_next_step_for_display(),
                "step_count": len(self._steps),
                "current_step_index": self._current_step_index,
            }


# 全域 session（單一眼鏡連線假設）
_nav_session = NavigationSession()


def get_nav_session() -> NavigationSession:
    return _nav_session
