"""
yolomedia — 可插拔推論適配層（weights-only）

使用 ultralytics YOLO 載入 yoloe-11l-seg.pt 權重，
提供 `process_single_frame(img, target)` 介面給 item_search_worker 呼叫。

回傳格式：
  (direction: str, speech: str)  或
  {"direction": ..., "speech": ..., "confidence": ...}
"""

from __future__ import annotations

import os
import threading
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
    from ultralytics import YOLO  # type: ignore[import-untyped]
except ImportError:
    YOLO = None  # type: ignore[assignment]

try:
    import numpy as np  # type: ignore[import-untyped]
except ImportError:
    np = None  # type: ignore[assignment]


_model_lock = threading.Lock()
_model: Optional[Any] = None
_model_path: str = ""

_CONF_THRESH = float(os.environ.get("YOLOMEDIA_CONF_THRESH", "0.35"))
_IOU_THRESH = float(os.environ.get("YOLOMEDIA_IOU_THRESH", "0.45"))

_last_detections: List[Dict[str, Any]] = []
_last_detections_lock = threading.Lock()


def _get_model_path() -> str:
    p = (getattr(config, "YOLOE_MODEL_PATH", "") or "").strip()
    if p:
        return p
    candidates = [
        Path(__file__).parent / "models" / "yoloe-11l-seg.pt",
        Path(__file__).parent / "models" / "yolo-seg.pt",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return ""


def _ensure_model() -> Optional[Any]:
    global _model, _model_path
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        if YOLO is None:
            return None
        path = _get_model_path()
        if not path or not Path(path).exists():
            return None
        try:
            _model = YOLO(path)
            _model_path = path
            print(f"[yolomedia] Model loaded: {path}")
            return _model
        except Exception as e:
            print(f"[yolomedia] Failed to load model: {e}")
            return None


def _bbox_center(x1: float, y1: float, x2: float, y2: float) -> Tuple[float, float]:
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def _direction_from_position(
    cx: float, cy: float, img_w: int, img_h: int, tolerance: float = 0.25
) -> str:
    rx = cx / img_w
    ry = cy / img_h

    if (0.5 - tolerance) <= rx <= (0.5 + tolerance) and (0.5 - tolerance) <= ry <= (0.5 + tolerance):
        return "OK"
    if rx < 0.5 - tolerance:
        return "向左"
    if rx > 0.5 + tolerance:
        return "向右"
    if ry < 0.5 - tolerance:
        return "向上"
    if ry > 0.5 + tolerance:
        return "向下"
    return "向前"


def _match_target(class_name: str, target: str) -> bool:
    if not target:
        return True
    t = target.lower().strip()
    c = class_name.lower().strip()
    return t in c or c in t


def process_single_frame(
    img: Any, target: str = ""
) -> Dict[str, Any]:
    """
    主要推論入口。

    Parameters:
        img: BGR numpy array (from cv2)
        target: 使用者指定的目標名稱（可為空，空則回傳最高信度物件）

    Returns:
        {"direction": str, "speech": str, "confidence": float, "detections": [...]}
    """
    model = _ensure_model()
    if model is None:
        return {"direction": "unknown", "speech": "", "confidence": 0.0, "detections": []}

    if np is None or img is None:
        return {"direction": "unknown", "speech": "", "confidence": 0.0, "detections": []}

    h, w = img.shape[:2]

    try:
        results = model(img, conf=_CONF_THRESH, iou=_IOU_THRESH, verbose=False)
    except Exception:
        return {"direction": "unknown", "speech": "", "confidence": 0.0, "detections": []}

    if not results:
        return {"direction": "unknown", "speech": "畫面中未偵測到物件。", "confidence": 0.0, "detections": []}

    r = results[0]
    names = getattr(r, "names", None) or getattr(model, "names", None) or {}
    boxes = getattr(r, "boxes", None)
    if boxes is None:
        return {"direction": "unknown", "speech": "畫面中未偵測到物件。", "confidence": 0.0, "detections": []}

    xyxy = getattr(boxes, "xyxy", None)
    conf = getattr(boxes, "conf", None)
    cls = getattr(boxes, "cls", None)
    if xyxy is None or conf is None or cls is None or len(cls) == 0:
        return {"direction": "unknown", "speech": "畫面中未偵測到物件。", "confidence": 0.0, "detections": []}

    all_dets: List[Dict[str, Any]] = []
    for i in range(len(cls)):
        try:
            cid = int(cls[i])
            score = float(conf[i])
            x1, y1, x2, y2 = [float(v) for v in xyxy[i].tolist()]
        except Exception:
            continue
        name = str(names.get(cid, cid)) if isinstance(names, dict) else str(cid)
        all_dets.append({
            "class": name,
            "confidence": round(score, 3),
            "bbox": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
        })

    with _last_detections_lock:
        _last_detections.clear()
        _last_detections.extend(all_dets)

    matched = [d for d in all_dets if _match_target(d["class"], target)]
    if not matched:
        if target:
            speech = f"畫面中未找到「{target}」，請轉動方向。"
        else:
            speech = "畫面中未偵測到目標物件。"
        return {"direction": "unknown", "speech": speech, "confidence": 0.0, "detections": all_dets}

    best = max(matched, key=lambda d: d["confidence"])
    bx1, by1, bx2, by2 = best["bbox"]
    cx, cy = _bbox_center(bx1, by1, bx2, by2)
    direction = _direction_from_position(cx, cy, w, h)

    if direction == "OK":
        speech = f"已找到「{best['class']}」，就在前方可拿取的位置。"
    else:
        speech = f"「{best['class']}」在{direction}方向，請往{direction}移動。"

    return {
        "direction": direction,
        "speech": speech,
        "confidence": best["confidence"],
        "detections": all_dets,
    }


def get_last_detections() -> List[Dict[str, Any]]:
    with _last_detections_lock:
        return list(_last_detections)


def get_model_info() -> Dict[str, Any]:
    return {
        "loaded": _model is not None,
        "path": _model_path,
        "conf_thresh": _CONF_THRESH,
        "iou_thresh": _IOU_THRESH,
    }
