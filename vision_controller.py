"""
視覺導盲 controller（本專案沿用既有架構的「輕量融合版」）

目標：
1) 接收最新 JPEG bytes
2) 解碼成 BGR
3) 依照目前運行狀態（導航/紅綠燈/物品查找）在畫面上做疊字
4) 輸出 annotated JPEG bytes，供監控面板與 /ws/viewer 即時顯示

注意：
- 目前此 controller 不替代你的 GPS 導航/紅綠燈/Gemini item_search 的語音邏輯，
  而是「用來統一視覺狀態與疊字顯示」，避免先把整套上游 workflow 全量移植造成風險。
- 後續若你要做更高階的視覺狀態機，可把同樣的 annotated 輸出介面留著，
  內部再替換為上游 navigation_master 與 workflows。
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

import config

try:
    import cv2  # type: ignore[import-untyped]
    import numpy as np  # type: ignore[import-untyped]
except Exception:  # pragma: no cover
    cv2 = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]

from item_search_worker import get_snapshot as get_item_search_snapshot
from navigation_state import get_nav_session
from traffic_crossing import get_controller


class VisionController:
    def __init__(self) -> None:
        self._last_annotated: Optional[bytes] = None
        self._last_ts: float = 0.0
        self._frame_count: int = 0

        # 畫面疊字最低更新頻率
        self._interval_sec = float(getattr(config, "VISION_OVERLAY_INTERVAL_SEC", 0.35))
        # 額外：每 N 幀才解碼/疊字一次（降低解碼/運算）
        self._frame_skip_n = max(1, int(getattr(config, "VISION_FRAME_SKIP_N", 2)))
        # 若解碼失敗就跳過
        self._enabled = bool(getattr(config, "ENABLE_VISION_OVERLAY", True))

    def get_latest_annotated_frame_bytes(self, max_age_sec: float = 2.0) -> Optional[bytes]:
        if not self._enabled:
            return None
        if not self._last_annotated:
            return None
        if time.time() - self._last_ts > max_age_sec:
            return None
        return self._last_annotated

    def tick(self, frame_b: Optional[bytes]) -> None:
        """更新 annotated frame。"""
        if not self._enabled:
            return
        if not frame_b:
            return

        self._frame_count += 1
        if self._frame_skip_n > 1 and (self._frame_count % self._frame_skip_n) != 0:
            return

        # 節流：避免每次 frame 都解碼/疊字
        now = time.time()
        if now - self._last_ts < self._interval_sec:
            return

        if cv2 is None or np is None:
            return

        try:
            arr = np.frombuffer(frame_b, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                return

            annotated = self._overlay_state(img)
            ok, buf = cv2.imencode(".jpg", annotated, [int(getattr(config, "VISION_JPEG_QUALITY", 75))])
            if not ok:
                return
            self._last_annotated = buf.tobytes()
            self._last_ts = now
        except Exception:
            # 任何解碼/疊字錯誤都不影響主流程
            return

    def _overlay_state(self, img_bgr: Any) -> Any:
        nav = get_nav_session().get_snapshot()
        crossing = get_controller().get_state()
        item = get_item_search_snapshot()

        # 疊字區：左上角
        x = 10
        y = 30
        lh = 24

        # 半透明底
        try:
            cv2.rectangle(img_bgr, (x - 6, y - 18), (420, y + 120), (0, 0, 0), -1)
        except Exception:
            pass

        state = nav.get("state", "-")
        last_tts = nav.get("last_tts", "") or "-"
        next_step = nav.get("next_step") or {}
        next_ins = next_step.get("instruction") or "-"

        traffic_state = crossing.get("state", "-")
        last_color = crossing.get("last_color", "-")

        # item_search
        item_active = bool(item.get("active"))
        item_phase = item.get("phase", "-")
        item_target = item.get("target", "-") or "-"
        item_guidance = item.get("last_guidance", "-") or "-"

        lines = [
            f"Mode: {state}",
            f"TTS: {str(last_tts)[:28]}",
            f"Next: {str(next_ins)[:28]}",
            f"Cross: {traffic_state} / {last_color}",
            f"Item: {'ON' if item_active else 'OFF'} {item_phase}",
            f"Target: {str(item_target)[:18]}",
            f"Guide: {str(item_guidance)[:24]}",
        ]

        # 顏色：白字 + 黃點題字
        for i, line in enumerate(lines):
            y_i = y + i * lh
            color = (220, 220, 220)
            thickness = 1
            if line.startswith("Mode:"):
                color = (255, 215, 80)
                thickness = 2
            cv2.putText(img_bgr, line, (x, y_i), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, thickness, cv2.LINE_AA)

        return img_bgr

