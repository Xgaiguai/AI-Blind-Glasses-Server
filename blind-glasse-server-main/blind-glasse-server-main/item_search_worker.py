"""
物品查找 worker：
- 由 `main.py` 在收到語音 `ITEM_SEARCH` 時啟動
- 用背景 thread 週期性分析最新影像並把「引導語音」丟進 `tts_queue.enqueue()`
- 收到 `ITEM_FOUND` 時停止

目前 MVP 做法：
- 優先使用 Gemini（`gemini_client.analyze_scene`）產生引導方向與語音內容
- 若之後要接 upstream 的 YOLOE+MediaPipe+光流追蹤，可在 `_run_with_vision_models()` 補齊
"""

from __future__ import annotations

import re
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

import config
from gemini_client import analyze_scene

try:
    # 這些依賴未必都會安裝；未安裝時會直接走 Gemini fallback。
    import cv2  # type: ignore[import-untyped]
    import numpy as np  # type: ignore[import-untyped]
except Exception:  # pragma: no cover
    cv2 = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]


_lock = threading.Lock()
_stop = threading.Event()
_thread: Optional[threading.Thread] = None

_active = False
_target_name: Optional[str] = None
_phase = "idle"  # searching | guiding | centered | idle
_last_guidance: str = ""
_last_direction: str = ""
_last_tts_ts = 0.0
_last_update_ts = 0.0
_ok_consecutive = 0
_start_ts = 0.0
_auto_stop_spoken = False
_vision_status: str = "disabled"  # disabled|ready|missing_models|missing_backend|running|error


def is_active() -> bool:
    with _lock:
        return _active


def get_snapshot() -> Dict[str, Any]:
    with _lock:
        return {
            "active": _active,
            "target": _target_name,
            "phase": _phase,
            "last_guidance": _last_guidance,
            "last_direction": _last_direction,
            "last_update_ts": _last_update_ts,
            "ok_consecutive": _ok_consecutive,
            "vision_status": _vision_status,
        }


def _parse_direction_and_speech(model_text: str) -> Tuple[str, str]:
    """
    期望模型輸出單行格式：
      direction=<向左|向右|向上|向下|向前|OK>;speech=<一句話>

    若解析失敗，direction 回覆 "unknown"，speech 用原文。
    """
    if not model_text:
        return "unknown", ""

    # normalize whitespace
    t = " ".join(model_text.strip().split())

    # 抓 direction=...（容忍 Gemini 偶發少分隔）
    m_dir = re.search(r"direction\s*[:=]\s*([^;,\n]+)", t, flags=re.IGNORECASE)
    direction_raw = m_dir.group(1).strip() if m_dir else ""

    # 抓 speech=...
    m_speech = re.search(r"speech\s*[:=]\s*(.+)$", t, flags=re.IGNORECASE)
    speech = m_speech.group(1).strip() if m_speech else ""

    # 若沒有 speech=，嘗試把 direction 之後的剩餘當作 speech
    if not speech:
        # 例如：direction=OK speech=... 或 direction=OK; speech=...
        m_speech2 = re.search(r"(?:speech\s*[:=])?\s*(.+)$", t, flags=re.IGNORECASE)
        if m_speech2:
            speech = (m_speech2.group(1) or "").strip()

    # 統一 direction
    dir_map = {
        "ok": "OK",
        "已找到": "OK",
        "已找到目標": "OK",
        "拿到": "OK",
        "拿到它": "OK",
        "OK": "OK",
        "向前": "向前",
        "forward": "向前",
        "向左": "向左",
        "left": "向左",
        "向右": "向右",
        "right": "向右",
        "向上": "向上",
        "up": "向上",
        "向下": "向下",
        "down": "向下",
        "向前方": "向前",
    }

    direction = ""
    if direction_raw:
        direction = dir_map.get(direction_raw, direction_raw)

    valid_dirs = {"OK", "向前", "向左", "向右", "向上", "向下"}
    # 若仍無法辨識（例如 direction_raw 被抓成整段 "OK speech=..."），做關鍵字 fallback
    if not direction or direction not in valid_dirs:
        tl = t.lower()
        if "ok" in tl or "已找到" in t or "拿到" in t:
            direction = "OK"
        elif "向左" in t or "left" in tl:
            direction = "向左"
        elif "向右" in t or "right" in tl:
            direction = "向右"
        elif "向上" in t or "up" in tl:
            direction = "向上"
        elif "向下" in t or "down" in tl:
            direction = "向下"
        elif "向前" in t or "forward" in tl:
            direction = "向前"
        else:
            direction = "unknown"

    # speech 預設至少回傳原文，確保有語音輸出
    if not speech:
        speech = t
    return direction.strip(), speech.strip()


def _gemini_guidance_prompt(target: str) -> str:
    target_clean = (target or "").strip()
    target_text = target_clean if target_clean else "未知目標物品"
    return (
        "你是視障使用者的物品查找助手。請根據畫面：\n"
        f"目標物品：{target_text}\n"
        "請只輸出一行並遵循以下格式（不要任何其他文字）：\n"
        "direction=<向左|向右|向上|向下|向前|OK>;speech=<一句適合語音播報的中文句子>\n"
        "- direction=OK 表示目標物品已在可接近/可拿取的位置（或畫面中心附近）。\n"
        "- speech 請簡短、可執行、不要列舉太多。\n"
    )


def _try_vision_guidance(frame_b: bytes, target: str) -> Optional[Tuple[str, str]]:
    """
    預留：接上 upstream YOLOE+MediaPipe+光流追蹤後，這裡可回傳 (direction, speech)。

    目前此專案先以「可插拔」方式接上上游：
    - 如果你已把上游 `yolomedia` 以可 import 的介面放進專案（且提供我們預期的函式），就嘗試呼叫
    - 否則維持 Gemini fallback（優雅降級）
    """
    global _vision_status

    if not getattr(config, "ENABLE_ITEM_SEARCH_VISION", False):
        with _lock:
            _vision_status = "disabled"
        return None

    yolo_path = (getattr(config, "YOLOE_MODEL_PATH", "") or "").strip()
    if not yolo_path:
        with _lock:
            _vision_status = "missing_models"
        return None

    if cv2 is None or np is None:
        with _lock:
            _vision_status = "missing_backend"
        return None

    try:
        # 嘗試呼叫可插拔介面：你未來若把上游封裝成可呼叫函式，這裡就會自動接上
        import importlib

        mod = importlib.import_module("yolomedia")

        candidates = [
            "process_single_frame",
            "process_frame",
            "infer_guidance",
            "detect_guidance",
        ]
        fn = None
        for name in candidates:
            if hasattr(mod, name):
                fn = getattr(mod, name)
                break

        if fn is None:
            with _lock:
                _vision_status = "missing_backend"
            return None

        # JPEG bytes -> BGR image
        arr = np.frombuffer(frame_b, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return None

        with _lock:
            _vision_status = "running"

        res = fn(img, target)

        if isinstance(res, tuple) and len(res) >= 2:
            return str(res[0]), str(res[1])
        if isinstance(res, dict):
            direction = res.get("direction")
            speech = res.get("speech")
            if direction is not None and speech is not None:
                return str(direction), str(speech)

        return None
    except Exception:
        with _lock:
            _vision_status = "error"
        return None


def start_item_search(
    target_name: str,
    get_frame_fn: Callable[[], Optional[bytes]],
    tts_enqueue_fn: Callable[[str], bool],
    analyze_scene_fn: Optional[Callable[..., str]] = None,
) -> None:
    """
    啟動 item_search worker（若已在跑，先停止再重啟）。
    """
    global _active, _target_name, _phase, _thread, _ok_consecutive, _start_ts, _auto_stop_spoken

    with _lock:
        # 重入時停止舊 worker
        if _thread and _thread.is_alive():
            _stop.set()
        _stop.clear()
        _active = True
        _target_name = target_name or ""
        _phase = "searching"
        _last_guidance = ""
        _last_direction = ""
        _last_tts_ts = 0.0
        _last_update_ts = time.time()
        _ok_consecutive = 0
        _start_ts = _last_update_ts
        _auto_stop_spoken = False

    # 若先前 thread 存在，等待它退出（避免重入同時跑）
    if _thread and _thread.is_alive():
        _thread.join(timeout=2.0)

    def run() -> None:
        try:
            _run_loop(get_frame_fn, tts_enqueue_fn, analyze_scene_fn or analyze_scene)
        finally:
            with _lock:
                # 結束後釋放 active
                _active = False
                _phase = "idle"

    _thread = threading.Thread(target=run, daemon=True)
    _thread.start()


def stop_item_search() -> None:
    global _active
    with _lock:
        if not _active:
            # 即使沒在跑，也維持語意一致
            return
        _active = False
        _phase = "idle"
        _target_name = None
    _stop.set()


def _run_loop(
    get_frame_fn: Callable[[], Optional[bytes]],
    tts_enqueue_fn: Callable[[str], bool],
    analyze_scene_fn: Callable[..., str],
) -> None:
    global _last_guidance, _last_direction, _phase, _last_update_ts, _last_tts_ts, _ok_consecutive, _auto_stop_spoken
    interval_sec = float(getattr(config, "ITEM_SEARCH_INTERVAL_SEC", "1.5"))
    min_tts_interval_sec = float(getattr(config, "ITEM_SEARCH_TTS_MIN_INTERVAL_SEC", "1.5"))
    auto_stop_enable = bool(getattr(config, "ITEM_SEARCH_AUTO_STOP_ENABLE", True))
    ok_consecutive_need = int(getattr(config, "ITEM_SEARCH_OK_CONSECUTIVE_COUNT", 3))
    max_seconds = float(getattr(config, "ITEM_SEARCH_MAX_SECONDS", 90))

    while not _stop.is_set():
        with _lock:
            if not _active:
                break
            target = _target_name or ""
            start_ts = _start_ts

        frame_b = get_frame_fn()
        if not frame_b:
            time.sleep(0.25)
            continue

        now = time.time()
        direction: str = "unknown"
        speech: str = ""

        # 超時保護：避免無限播報
        if max_seconds > 0 and (now - start_ts) > max_seconds:
            if tts_enqueue_fn("搜尋物品已超时，請稍後再試。"):
                with _lock:
                    _last_tts_ts = now
            stop_item_search()
            break

        # 先嘗試視覺模型（若後續你接上 YOLOE+MediaPipe）
        if getattr(config, "ENABLE_ITEM_SEARCH_VISION", False):
            try:
                vis = _try_vision_guidance(frame_b, target)
                if vis is not None:
                    direction, speech = vis
            except Exception:
                # 視覺模型失敗不影響，直接 Gemini fallback
                direction, speech = "unknown", ""

        # Gemini fallback：產出 direction + speech
        if not speech:
            prompt = _gemini_guidance_prompt(target)
            try:
                # 允許 analyze_scene_fn 在測試時被注入
                try:
                    speech_text = analyze_scene_fn(frame_b, extra_prompt=prompt)
                except TypeError:
                    speech_text = analyze_scene_fn(frame_b, prompt)
            except Exception:
                speech_text = "目前辨識暫不可用，請稍後再試。"
            direction, speech = _parse_direction_and_speech(speech_text)

        # 更新狀態（供 monitor）
        with _lock:
            _last_direction = direction
            _last_guidance = speech
            _last_update_ts = now
            if direction == "OK":
                _phase = "centered"
                _ok_consecutive += 1
            elif direction in ("向左", "向右", "向上", "向下", "向前"):
                _phase = "guiding"
                _ok_consecutive = 0
            else:
                _phase = "searching"
                _ok_consecutive = 0
            ok_count = _ok_consecutive

        # Auto OK stop（連續達標後停止）
        if auto_stop_enable and ok_consecutive_need > 0 and direction == "OK" and ok_count >= ok_consecutive_need:
            final_speech = "已找到，請拿取。"
            # 結束語音：強制只講一次，避免一般節流導致漏講
            do_enqueue_final = False
            with _lock:
                if not _auto_stop_spoken and final_speech:
                    _auto_stop_spoken = True
                    _last_tts_ts = now
                    do_enqueue_final = True
            if do_enqueue_final:
                tts_enqueue_fn(final_speech)
            stop_item_search()
            break

        # 語音節流（未觸發 auto-stop 才播）
        with _lock:
            should_say = (now - _last_tts_ts) >= min_tts_interval_sec
        if should_say and speech:
            if tts_enqueue_fn(speech):
                with _lock:
                    _last_tts_ts = now

        time.sleep(interval_sec)

