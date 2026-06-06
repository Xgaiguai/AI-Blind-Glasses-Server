"""
Vision controller:
1. Decode the latest JPEG frame.
2. Run the configured YOLO .pt model(s).
3. Draw state text and detection boxes for /monitor, /ws/viewer, and /api/monitor/frame.
"""

from __future__ import annotations

import time
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import config

_LOCAL_CACHE_DIR = Path(__file__).resolve().parent / ".local_cache"
_ULTRALYTICS_CONFIG_DIR = _LOCAL_CACHE_DIR / "ultralytics"
_MPL_CONFIG_DIR = _LOCAL_CACHE_DIR / "matplotlib"
_ULTRALYTICS_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
_MPL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("YOLO_CONFIG_DIR", str(_ULTRALYTICS_CONFIG_DIR))
os.environ.setdefault("MPLCONFIGDIR", str(_MPL_CONFIG_DIR))

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


Detection = Tuple[int, int, int, int, str, float, str]


class VisionOverlayDetector:
    """Load YOLO .pt models and return detections for the monitor overlay."""

    def __init__(self) -> None:
        self._model_paths = self._resolve_model_paths()
        self._conf = float(getattr(config, "VISION_DETECT_CONF_THRES", 0.35))
        self._iou = float(getattr(config, "VISION_DETECT_IOU_THRES", 0.45))
        self._target_classes = {
            str(x).strip().lower()
            for x in (getattr(config, "VISION_TARGET_CLASSES", []) or [])
            if str(x).strip()
        }
        self._models: List[Tuple[str, Any]] = []
        self._load_attempted = False
        self._last_detections: List[Dict[str, Any]] = []
        self._last_error = ""
        self._enabled = bool(self._model_paths and YOLO is not None)

    def _resolve_model_paths(self) -> List[str]:
        configured = [
            str(p).strip()
            for p in (getattr(config, "VISION_MODEL_PATHS", []) or [])
            if str(p).strip()
        ]
        legacy = str(getattr(config, "BLIND_TILE_MODEL_PATH", "") or "").strip()
        candidates = configured or ([legacy] if legacy else [])
        base_dir = Path(__file__).resolve().parent
        out: List[str] = []
        seen = set()
        for raw in candidates:
            path = Path(raw)
            if not path.is_absolute():
                path = base_dir / path
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            if path.exists():
                out.append(key)
        return out

    def _ensure_models(self) -> bool:
        if not self._enabled:
            return False
        if self._models:
            return True
        if self._load_attempted:
            return False
        self._load_attempted = True
        for path in self._model_paths:
            try:
                model = YOLO(path)
                self._models.append((path, model))
                print(f"[vision] YOLO overlay model loaded: {path}")
            except Exception as e:
                self._last_error = str(e)
                print(f"[vision] Failed to load YOLO overlay model {path}: {e}")
        return bool(self._models)

    def detect(self, img_bgr: Any) -> List[Detection]:
        if not self._ensure_models():
            return []

        detections: List[Detection] = []
        for model_path, model in self._models:
            try:
                results = model(img_bgr, conf=self._conf, iou=self._iou, verbose=False)
                if not results:
                    continue
                r = results[0]
                names = getattr(r, "names", None) or getattr(model, "names", None) or {}
                boxes = getattr(r, "boxes", None)
                if boxes is None:
                    continue
                xyxy = getattr(boxes, "xyxy", None)
                conf = getattr(boxes, "conf", None)
                cls = getattr(boxes, "cls", None)
                if xyxy is None or conf is None or cls is None:
                    continue
            except Exception as e:
                self._last_error = str(e)
                continue

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
                detections.append((x1, y1, x2, y2, name, score, Path(model_path).name))

        self._last_detections = [
            {
                "class": name,
                "confidence": round(score, 3),
                "bbox": [x1, y1, x2, y2],
                "model": model_name,
            }
            for x1, y1, x2, y2, name, score, model_name in detections
        ]
        return detections

    def get_summary(self) -> Dict[str, Any]:
        self._ensure_models()
        top_k = sorted(self._last_detections, key=lambda d: d["confidence"], reverse=True)[:5]
        return {
            "model_loaded": bool(self._models),
            "model_path": ", ".join(path for path, _ in self._models),
            "configured_paths": self._model_paths,
            "last_target": top_k[0]["class"] if top_k else None,
            "last_confidence": top_k[0]["confidence"] if top_k else 0.0,
            "detection_count": len(self._last_detections),
            "top_k": top_k,
            "last_error": self._last_error,
        }


class VisionController:
    def __init__(self) -> None:
        self._last_annotated: Optional[bytes] = None
        self._last_ts: float = 0.0
        self._frame_count: int = 0
        self._interval_sec = float(getattr(config, "VISION_OVERLAY_INTERVAL_SEC", 0.35))
        self._frame_skip_n = max(1, int(getattr(config, "VISION_FRAME_SKIP_N", 2)))
        self._enabled = bool(getattr(config, "ENABLE_VISION_OVERLAY", True))
        self._overlay_detector = VisionOverlayDetector()

    def get_latest_annotated_frame_bytes(self, max_age_sec: float = 2.0) -> Optional[bytes]:
        if not self._enabled:
            return None
        if not self._last_annotated:
            return None
        if time.time() - self._last_ts > max_age_sec:
            return None
        return self._last_annotated

    def get_detection_summary(self) -> Dict[str, Any]:
        return self._overlay_detector.get_summary()

    def tick(self, frame_b: Optional[bytes]) -> None:
        if not self._enabled or not frame_b:
            return

        self._frame_count += 1
        if self._frame_skip_n > 1 and (self._frame_count % self._frame_skip_n) != 0:
            return

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

            detections = self._overlay_detector.detect(img)
            annotated = self._overlay_state(img)
            if detections:
                self._draw_detection_boxes(annotated, detections)
            ok, buf = cv2.imencode(".jpg", annotated, [int(getattr(config, "VISION_JPEG_QUALITY", 75))])
            if not ok:
                return
            self._last_annotated = buf.tobytes()
            self._last_ts = now
        except Exception:
            return

    def _overlay_state(self, img_bgr: Any) -> Any:
        nav = get_nav_session().get_snapshot()
        crossing = get_controller().get_state()
        item = get_item_search_snapshot()

        x = 10
        y = 30
        lh = 24

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

        for i, line in enumerate(lines):
            y_i = y + i * lh
            color = (220, 220, 220)
            thickness = 1
            if line.startswith("Mode:"):
                color = (255, 215, 80)
                thickness = 2
            cv2.putText(img_bgr, line, (x, y_i), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, thickness, cv2.LINE_AA)

        return img_bgr

    def _draw_detection_boxes(self, img_bgr: Any, detections: List[Detection]) -> None:
        palette = {
            "crosswalk": (0, 170, 255),
            "road_crossing": (0, 170, 255),
            "tactile_paving": (0, 255, 120),
            "blind_brick": (0, 255, 120),
            "blind_path": (0, 255, 120),
            "traffic_light": (0, 255, 255),
            "blank": (150, 150, 150),
            "countdown_blank": (150, 150, 150),
            "countdown_go": (0, 220, 0),
            "countdown_stop": (0, 0, 255),
            "crossing": (255, 180, 0),
            "go": (0, 220, 0),
            "stop": (0, 0, 255),
            "shotput": (255, 90, 180),
        }
        for x1, y1, x2, y2, name, score, _model_name in detections:
            color = palette.get(name, (255, 60, 40))
            cv2.rectangle(img_bgr, (x1, y1), (x2, y2), color, 2)
            label = f"{name} {score:.2f} [{_model_name}]"
            (tw, th), _baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
            y_text = y1 - 8 if y1 - 8 > th + 8 else y1 + th + 12
            cv2.rectangle(img_bgr, (x1, y_text - th - 7), (x1 + tw + 8, y_text + 4), color, -1)
            cv2.putText(
                img_bgr,
                label,
                (x1 + 4, y_text),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0, 0, 0),
                2,
                cv2.LINE_AA,
            )
