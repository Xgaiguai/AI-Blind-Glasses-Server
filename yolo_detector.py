"""
YOLOv8 ONNX 目標偵測，篩選 person, car, motorcycle, dog，並產出避障提醒文字。
"""

from pathlib import Path
from typing import List, Optional, Tuple

import cv2  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]
import onnxruntime as ort  # type: ignore[import-untyped]

import config

# COCO 類別 ID
COCO_CLASS_IDS = {"person": 0, "car": 2, "motorcycle": 3, "dog": 16}
COCO_ID_TO_NAME = {v: k for k, v in COCO_CLASS_IDS.items()}
TARGET_IDS = [COCO_CLASS_IDS[c] for c in config.YOLO_TARGET_CLASSES if c in COCO_CLASS_IDS]


def _nms_boxes(boxes: np.ndarray, scores: np.ndarray, iou_thresh: float) -> np.ndarray:
    """NMS on xyxy boxes, returns indices to keep."""
    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)
        if order.size == 1:
            break
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0, xx2 - xx1)
        h = np.maximum(0, yy2 - yy1)
        inter = w * h
        iou = inter / (areas[i] + areas[order[1:]] - inter)
        inds = np.where(iou <= iou_thresh)[0]
        order = order[inds + 1]
    return np.array(keep)


class YOLODetector:
    def __init__(
        self,
        onnx_path: Optional[str] = None,
        input_size: Tuple[int, int] = (320, 320),
        conf_thresh: float = 0.45,
        iou_thresh: float = 0.45,
    ) -> None:
        onnx_path = onnx_path or config.YOLO_ONNX_PATH
        self.input_size = input_size or config.YOLO_INPUT_SIZE
        self.conf_thresh = conf_thresh or config.YOLO_CONF_THRESH
        self.iou_thresh = iou_thresh or config.YOLO_IOU_THRESH
        self.session = None
        self.input_name = None
        path = Path(onnx_path)
        if path.exists():
            self.session = ort.InferenceSession(
                str(path),
                providers=["CPUExecutionProvider"],
            )
            self.input_name = self.session.get_inputs()[0].name
        else:
            print(f"[YOLO] Model not found: {onnx_path}, detector disabled.")

    def _preprocess(self, image: np.ndarray) -> Tuple[np.ndarray, float, int, int]:
        """Resize to input_size, NCHW, normalize 0-1. Returns (tensor, scale, orig_w, orig_h)."""
        h, w = image.shape[:2]
        inp = cv2.resize(image, self.input_size)
        inp = cv2.cvtColor(inp, cv2.COLOR_BGR2RGB)
        inp = inp.transpose(2, 0, 1)
        inp = np.ascontiguousarray(inp).astype(np.float32) / 255.0
        inp = np.expand_dims(inp, axis=0)
        scale = min(self.input_size[0] / w, self.input_size[1] / h)
        return inp, scale, w, h

    def _postprocess(
        self, output: np.ndarray, scale: float, orig_w: int, orig_h: int
    ) -> List[Tuple[int, float, Tuple[float, float, float, float]]]:
        """output shape (1, 84, N). Returns list of (class_id, conf, (x1,y1,x2,y2) in orig image)."""
        out = output[0]
        if out.ndim == 2:
            out = out.T
        n = out.shape[0]
        boxes_xywh = out[:, :4]
        class_scores = out[:, 4:]
        # 還原到 input 尺寸的 xyxy
        cx = boxes_xywh[:, 0]
        cy = boxes_xywh[:, 1]
        w = boxes_xywh[:, 2]
        h = boxes_xywh[:, 3]
        x1 = (cx - w / 2)
        y1 = (cy - h / 2)
        x2 = (cx + w / 2)
        y2 = (cy + h / 2)
        # 縮放到原始圖
        sx = orig_w / self.input_size[0]
        sy = orig_h / self.input_size[1]
        x1, x2 = x1 * sx, x2 * sx
        y1, y2 = y1 * sy, y2 * sy
        results = []
        for cid in TARGET_IDS:
            if cid >= class_scores.shape[1]:
                continue
            scores = class_scores[:, cid]
            mask = scores >= self.conf_thresh
            if not np.any(mask):
                continue
            inds = np.where(mask)[0]
            boxes = np.stack([x1[inds], y1[inds], x2[inds], y2[inds]], axis=1)
            sc = scores[inds]
            keep = _nms_boxes(boxes, sc, self.iou_thresh)
            for i in keep:
                results.append((cid, float(sc[i]), (float(x1[inds[i]]), float(y1[inds[i]]), float(x2[inds[i]]), float(y2[inds[i]]))))
        return results

    def run_inference(self, image: np.ndarray) -> List[Tuple[int, float, Tuple[float, float, float, float]]]:
        """輸入 BGR 圖，回傳 [(class_id, conf, (x1,y1,x2,y2)), ...]。"""
        if self.session is None:
            return []
        inp, scale, orig_w, orig_h = self._preprocess(image)
        out = self.session.run(None, {self.input_name: inp})
        output = out[0] if isinstance(out[0], np.ndarray) else np.array(out[0])
        return self._postprocess(output, scale, orig_w, orig_h)

    def analyze_for_obstacle(
        self,
        detections: List[Tuple[int, float, Tuple[float, float, float, float]]],
        image_width: int,
        image_height: int,
    ) -> Optional[str]:
        """若偵測到物體在畫面中心且佔比大，回傳避障提醒文字。"""
        if not detections or image_width <= 0 or image_height <= 0:
            return None
        center_ratio = getattr(config, "OBSTACLE_CENTER_RATIO", 0.4)
        area_ratio_min = getattr(config, "OBSTACLE_AREA_RATIO_MIN", 0.05)
        total = image_width * image_height
        cx_lo = image_width * (0.5 - center_ratio / 2)
        cx_hi = image_width * (0.5 + center_ratio / 2)
        cy_lo = image_height * (0.5 - center_ratio / 2)
        cy_hi = image_height * (0.5 + center_ratio / 2)
        for cid, conf, (x1, y1, x2, y2) in detections:
            box_cx = (x1 + x2) / 2
            box_cy = (y1 + y2) / 2
            if not (cx_lo <= box_cx <= cx_hi and cy_lo <= box_cy <= cy_hi):
                continue
            area = (x2 - x1) * (y2 - y1)
            if area / total < area_ratio_min:
                continue
            name = COCO_ID_TO_NAME.get(cid, "物體")
            return f"前方有{name}，距離較近，請注意。"
        return None


# 單例
_detector: Optional[YOLODetector] = None


def get_detector() -> YOLODetector:
    global _detector
    if _detector is None:
        _detector = YOLODetector()
    return _detector
