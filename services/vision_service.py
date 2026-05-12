"""
視覺服務：統一管理影像取得、YOLO 避障推論、annotated frame 疊字。
從 main.py 的全域邏輯抽離，降低耦合。
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

import cv2  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]

from stream_manager import stream_manager
from vision_controller import VisionController
from yolo_detector import get_detector


class VisionService:
    def __init__(self) -> None:
        self._obstacle_lock = threading.Lock()
        self._latest_obstacle_text: Optional[str] = None
        self._controller = VisionController()

    def get_raw_frame(self) -> Optional[bytes]:
        frame_b, _ = stream_manager.get_latest_frame()
        if not frame_b or not stream_manager.has_recent_frame():
            return None
        return frame_b

    def get_viewer_frame(self) -> Optional[bytes]:
        try:
            annotated = self._controller.get_latest_annotated_frame_bytes()
            if annotated:
                return annotated
        except Exception:
            pass
        return self.get_raw_frame()

    def get_obstacle_text(self) -> Optional[str]:
        with self._obstacle_lock:
            return self._latest_obstacle_text

    def run_yolo_once(self) -> Optional[str]:
        frame_b = self.get_raw_frame()
        if not frame_b:
            return None
        try:
            det = get_detector()
            arr = np.frombuffer(frame_b, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                return None
            h, w = img.shape[:2]
            detections = det.run_inference(img)
            text = det.analyze_for_obstacle(detections, w, h)
            with self._obstacle_lock:
                self._latest_obstacle_text = text
            return text
        except Exception:
            return None

    def tick_overlay(self) -> None:
        frame_b = self.get_raw_frame()
        if frame_b:
            self._controller.tick(frame_b)
