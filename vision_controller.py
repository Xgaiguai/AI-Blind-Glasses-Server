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
from typing import Any, Dict, List, Optional, Tuple

import config

try:
    import cv2  # type: ignore[import-untyped]
    import numpy as np  # type: ignore[import-untyped]
except Exception:  # pragma: no cover
    cv2 = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]

try:
    from ultralytics import YOLO  # type: ignore[import-untyped]
except Exception:  # pragma: no cover
    YOLO = None  # type: ignore[assignment]

from item_search_worker import get_snapshot as get_item_search_snapshot
from navigation_state import get_nav_session
from traffic_crossing import get_controller


class BlindTileDetector:
    """可選：導盲磚/斑馬線模型，輸出可視化框供 monitor 顯示。"""

    def __init__(self) -> None:
        self._model_path = str(getattr(config, "BLIND_TILE_MODEL_PATH", "") or "").strip()
        self._conf = float(getattr(config, "BLIND_TILE_CONF_THRES", 0.35))
        self._iou = float(getattr(config, "BLIND_TILE_IOU_THRES", 0.45))
        self._target_classes = {
            str(x).strip().lower() for x in (getattr(config, "BLIND_TILE_TARGET_CLASSES", []) or []) if str(x).strip()
        }
        self._model: Optional[Any] = None
        self._enabled = bool(self._model_path and YOLO is not None)

    def _ensure_model(self) -> bool:
        if not self._enabled:
            return False
        if self._model is not None:
            return True
        try:
            self._model = YOLO(self._model_path)
            return True
        except Exception:
            self._model = None
            return False

    def detect(self, img_bgr: Any) -> List[Tuple[int, int, int, int, str, float]]:
        """
        回傳框清單：(x1, y1, x2, y2, class_name, conf)
        """
        if not self._ensure_model():
            return []
        try:
            results = self._model(img_bgr, conf=self._conf, iou=self._iou, verbose=False)
            if not results:
                return []
            r = results[0]
            names = getattr(r, "names", None) or getattr(self._model, "names", None) or {}
            boxes = getattr(r, "boxes", None)
            if boxes is None:
                return []
            xyxy = getattr(boxes, "xyxy", None)
            conf = getattr(boxes, "conf", None)
            cls = getattr(boxes, "cls", None)
            if xyxy is None or conf is None or cls is None:
                return []

            out: List[Tuple[int, int, int, int, str, float]] = []
            for i in range(len(cls)):
                try:
                    cid = int(cls[i])
                    score = float(conf[i])
                    x1, y1, x2, y2 = [int(v) for v in xyxy[i].tolist()]
                except Exception:
                    continue
                name = str(names.get(cid, cid)).lower() if isinstance(names, dict) else str(cid).lower()
                if self._target_classes and name not in self._target_classes:
                    continue
                out.append((x1, y1, x2, y2, name, score))
            return out
        except Exception:
            return []


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
        self._blind_tile_detector = BlindTileDetector()

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

            detections = self._blind_tile_detector.detect(img)
            annotated = self._overlay_state(img)
            if detections:
                self._draw_blind_tile_boxes(annotated, detections)
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

    def _draw_blind_tile_boxes(
        self,
        img_bgr: Any,
        detections: List[Tuple[int, int, int, int, str, float]],
    ) -> None:
        for x1, y1, x2, y2, name, score in detections:
            cv2.rectangle(img_bgr, (x1, y1), (x2, y2), (255, 60, 40), 2)
            label = f"{name} {score:.2f}"
            y_text = y1 - 8 if y1 - 8 > 10 else y1 + 20
            cv2.putText(
                img_bgr,
                label,
                (x1, y_text),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                (255, 60, 40),
                2,
                cv2.LINE_AA,
            )

