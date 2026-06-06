"""
紅綠燈 / 過馬路流程（簡化版，僅紅綠燈判斷與語音提示）。

設計目標：
- 不引入 YOLO，完全使用現有 Gemini 影像分析。
- 具備穩定性：使用多幀多數表決避免單幀誤判。
- 提供簡單狀態：WAIT（等待燈色）、GO（綠燈可通行）、RECHECK（通行中定期複查）。

用法（由 main.py 呼叫）：
- get_controller().start()      # 啟動流程（例如語音「紅綠燈」後）
- 由背景執行緒固定頻率呼叫 get_controller().tick(get_frame_fn, tts_enqueue_fn)
"""

import enum
import os
import time
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

import config
from gemini_client import analyze_traffic_light

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


class CrossingState(enum.Enum):
    IDLE = "idle"
    WAIT = "wait"
    GO = "go"
    RECHECK = "recheck"


class MajorityFilter:
    """簡單多數表決，用於穩定紅綠燈顏色輸出。"""

    def __init__(self, size: int = 8) -> None:
        self._buf: Deque[str] = deque(maxlen=size)

    def push(self, v: str) -> None:
        self._buf.append(v)

    def majority(self) -> str:
        if not self._buf:
            return "unknown"
        cnt: Dict[str, int] = {}
        for v in self._buf:
            cnt[v] = cnt.get(v, 0) + 1
        # unknown 權重最低
        items = sorted(cnt.items(), key=lambda x: (0 if x[0] == "unknown" else 1, x[1]), reverse=True)
        return items[0][0]

    def clear(self) -> None:
        self._buf.clear()

    def history(self) -> List[str]:
        return list(self._buf)


def _parse_traffic_color(text: str) -> str:
    """
    將 Gemini 回覆文字解析為標準顏色：red/green/yellow/unknown。
    只看關鍵字，避免被多餘描述干擾。
    """
    t = (text or "").strip().lower()
    if not t:
        return "unknown"
    # 以中文為主，兼容簡單英文
    if ("紅燈" in t) or ("red" in t and "light" in t):
        return "red"
    if ("綠燈" in t) or ("green" in t and "light" in t):
        return "green"
    if ("黃燈" in t) or ("黃燈" in t) or ("yellow" in t and "light" in t):
        return "yellow"
    if "無法判斷" in t or "unknown" in t or "看不出" in t:
        return "unknown"
    return "unknown"


# ---- 可選：YOLO 紅綠燈偵測 ----
_TRAFFIC_LIGHT_YOLO_MODEL_PATH = (
    getattr(config, "TRAFFIC_LIGHT_YOLO_MODEL_PATH", "")
    or os.environ.get("TRAFFIC_LIGHT_YOLO_MODEL_PATH", "")
)

_YOLO_CONF_THRES = float(getattr(config, "TRAFFIC_LIGHT_YOLO_CONF_THRES", 0.25))
_yolo_model: Optional[Any] = None
_yolo_ready = False


def _try_yolo_color(bgr_img: Any) -> str:
    """
    透過 YOLO 模型回傳 red/green/yellow/unknown。
    若模型或依賴不可用則回傳 unknown（由外層 fallback 到 Gemini）。
    """
    global _yolo_model, _yolo_ready

    if YOLO is None or cv2 is None or np is None:
        return "unknown"
    if not _TRAFFIC_LIGHT_YOLO_MODEL_PATH:
        return "unknown"
    if not os.path.exists(_TRAFFIC_LIGHT_YOLO_MODEL_PATH):
        return "unknown"

    if not _yolo_ready:
        try:
            _yolo_model = YOLO(_TRAFFIC_LIGHT_YOLO_MODEL_PATH)
            _yolo_ready = True
        except Exception:
            _yolo_ready = False
            return "unknown"

    try:
        # Ultralytics 對 BGR/uint8 img 通常可直接處理
        results = _yolo_model(bgr_img, conf=_YOLO_CONF_THRES, verbose=False)
        if not results:
            return "unknown"
        r = results[0]
        names = getattr(r, "names", None) or getattr(_yolo_model, "names", None) or {}
        boxes = getattr(r, "boxes", None)
        if boxes is None:
            return "unknown"

        cls = getattr(boxes, "cls", None)
        conf = getattr(boxes, "conf", None)
        if cls is None or conf is None:
            return "unknown"

        best_color = "unknown"
        best_conf = 0.0
        for i in range(len(cls)):
            try:
                cid = int(cls[i])
                cconf = float(conf[i])
            except Exception:
                continue
            name = str(names.get(cid, cid)).lower() if isinstance(names, dict) else str(cid).lower()

            color = "unknown"
            if "red" in name or "stop" in name:
                color = "red"
            elif "green" in name or name in ("go",):
                color = "green"
            elif "yellow" in name or "amber" in name or "countdown" in name or "wait" in name:
                # 模型可能把倒計時也拆成類別，統一視為 yellow/unknown→yellow
                if "stop" in name or "red" in name:
                    color = "red"
                else:
                    color = "yellow"

            # 嚴格：僅允許 red/green/yellow
            if color not in ("red", "green", "yellow"):
                color = "unknown"

            if color != "unknown" and cconf > best_conf:
                best_conf = cconf
                best_color = color

        return best_color
    except Exception:
        return "unknown"


class TrafficCrossingController:
    """
    紅綠燈 / 過馬路流程控制器。

    只維護最小必要狀態與語音提示，避免干擾 GPS 導航。
    """

    def __init__(self) -> None:
        self._state = CrossingState.IDLE
        self._major = MajorityFilter(size=8)
        self._last_color = "unknown"
        self._last_tts_text = ""
        self._last_tts_ts = 0.0
        self._cooldown_until = 0.0
        self._go_started_ts: Optional[float] = None
        self._last_check_ts = 0.0

        # 可調參數
        self._confirm_frames = getattr(config, "CROSSING_CONFIRM_FRAMES", 3)
        self._min_tts_interval = 1.5  # 秒
        self._recheck_interval = 3.0  # GO / RECHECK 狀態下幾秒檢查一次
        self._max_go_duration = 60.0  # 最長 GO+RECHECK 秒數，時間到自動結束

    # ----- 對外 API -----

    def get_state(self) -> Dict[str, Any]:
        """給監控介面使用的狀態快照。"""
        return {
            "state": self._state.value,
            "last_color": self._last_color,
            "last_tts_text": self._last_tts_text,
            "history": self._major.history(),
        }

    def start(self) -> None:
        """啟動紅綠燈流程。"""
        self._state = CrossingState.WAIT
        self._major.clear()
        self._last_color = "unknown"
        self._last_tts_text = ""
        self._last_tts_ts = 0.0
        self._cooldown_until = time.time()  # 立即可說話
        self._go_started_ts = None
        self._last_check_ts = 0.0

    def stop(self) -> None:
        """強制結束流程。"""
        self._state = CrossingState.IDLE
        self._major.clear()
        self._last_color = "unknown"
        self._last_tts_text = ""
        self._go_started_ts = None

    def is_active(self) -> bool:
        return self._state is not CrossingState.IDLE

    def tick(
        self,
        get_frame_fn: Callable[[], Optional[bytes]],
        tts_enqueue_fn: Callable[[str], bool],
    ) -> None:
        """
        由背景執行緒週期呼叫。
        - get_frame_fn: 取得最新 JPEG bytes，無畫面則回傳 None。
        - tts_enqueue_fn: 佇列語音文字。
        """
        if self._state is CrossingState.IDLE:
            return

        now = time.time()
        if now < self._cooldown_until:
            return

        frame_b = get_frame_fn()
        if not frame_b:
            return

        # 先嘗試 YOLO；失敗則回落 Gemini
        color = "unknown"
        if _TRAFFIC_LIGHT_YOLO_MODEL_PATH and cv2 is not None:
            try:
                arr = np.frombuffer(frame_b, dtype=np.uint8) if np is not None else None
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR) if arr is not None else None
                if img is not None:
                    color = _try_yolo_color(img)
            except Exception:
                color = "unknown"

        if color == "unknown":
            raw = analyze_traffic_light(frame_b)
            color = _parse_traffic_color(raw)

        self._major.push(color)
        major = self._major.majority()
        self._last_color = major

        # IDLE 以外狀態共同處理：GO 過久自動結束
        if self._go_started_ts is not None and (now - self._go_started_ts) > self._max_go_duration:
            self._say(tts_enqueue_fn, now, "紅綠燈偵測結束。")
            self.stop()
            return

        if self._state is CrossingState.WAIT:
            self._handle_wait(now, major, tts_enqueue_fn)
        elif self._state in (CrossingState.GO, CrossingState.RECHECK):
            self._handle_go_recheck(now, major, tts_enqueue_fn)

    # ----- 內部 -----

    def _say(self, tts_enqueue_fn: Callable[[str], bool], now: float, text: str) -> None:
        if not text:
            return
        if now - self._last_tts_ts < self._min_tts_interval:
            return
        if tts_enqueue_fn(text):
            self._last_tts_ts = now
            self._last_tts_text = text

    def _handle_wait(self, now: float, major: str, tts_enqueue_fn: Callable[[str], bool]) -> None:
        # 多數表決為綠燈，且最近幾幀都穩定綠燈才放行
        if major == "green":
            # 簡單檢查：「最近 confirm_frames 幀有大多數是 green」
            hist = self._major.history()
            recent = hist[-max(self._confirm_frames, 1) :]
            if recent and all(c == "green" for c in recent):
                self._say(tts_enqueue_fn, now, "綠燈，可以過馬路。")
                self._state = CrossingState.GO
                self._go_started_ts = now
                self._cooldown_until = now + 1.0
                self._last_check_ts = now
                return

        # 若一直無法判斷，偶爾提示一次
        if major == "unknown" and (now - self._last_tts_ts) > 8.0:
            self._say(tts_enqueue_fn, now, "暫時無法清楚辨識紅綠燈，請稍微調整視角。")

    def _handle_go_recheck(self, now: float, major: str, tts_enqueue_fn: Callable[[str], bool]) -> None:
        # 定期複查
        if now - self._last_check_ts < self._recheck_interval:
            return
        self._last_check_ts = now

        if major == "red":
            self._say(tts_enqueue_fn, now, "已變紅燈，請停止前進。")
            # 結束流程，避免持續說話
            self.stop()
            return

        # 綠燈持續，不多說，只在剛開始 GO 時已提示過
        if major == "green":
            # 可視需要偶爾提醒「仍是綠燈，可以繼續通行」
            return

        # 其他情況（unknown / yellow），輕度提醒
        if major in ("yellow", "unknown"):
            self._say(tts_enqueue_fn, now, "請注意紅綠燈變化，小心通行。")


_controller = TrafficCrossingController()


def get_controller() -> TrafficCrossingController:
    return _controller

