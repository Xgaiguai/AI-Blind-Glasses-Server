"""
Gemini key pool:
- 兩把 key 輪詢（round-robin）
- 失敗時回退下一把 key
"""

from __future__ import annotations

import threading
from typing import Any, Callable, List, Optional

import config

try:
    import google.generativeai as genai  # type: ignore[import-untyped]
    _HAS_GEMINI = True
except Exception:
    genai = None  # type: ignore[assignment]
    _HAS_GEMINI = False

_lock = threading.Lock()
_rr_idx = 0


def _keys() -> List[str]:
    k1 = (getattr(config, "GEMINI_API_KEY_1", "") or "").strip()
    k2 = (getattr(config, "GEMINI_API_KEY_2", "") or "").strip()
    legacy = (getattr(config, "GEMINI_API_KEY", "") or "").strip()
    out: List[str] = []
    for k in (k1, k2, legacy):
        if k and k not in out:
            out.append(k)
    return out


def has_key() -> bool:
    return len(_keys()) > 0 and _HAS_GEMINI


def _pick_order() -> List[str]:
    keys = _keys()
    if not keys:
        return []
    global _rr_idx
    with _lock:
        start = _rr_idx % len(keys)
        _rr_idx = (_rr_idx + 1) % len(keys)
    return [keys[(start + i) % len(keys)] for i in range(len(keys))]


def call_with_pool(fn: Callable[[Any], Any]) -> Optional[Any]:
    """
    fn(model) -> result
    會用輪詢 key 試一次，失敗時回退其他 key。
    """
    if not _HAS_GEMINI:
        return None
    keys = _pick_order()
    if not keys:
        return None
    model_name = getattr(config, "GEMINI_MODEL", "gemini-2.5-flash")
    last_err: Optional[Exception] = None
    for key in keys:
        try:
            genai.configure(api_key=key)  # type: ignore[attr-defined]
            model = genai.GenerativeModel(model_name)  # type: ignore[attr-defined]
            return fn(model)
        except Exception as e:
            last_err = e
            continue
    if last_err is not None:
        print(f"[GeminiPool] all keys failed: {last_err}")
    return None

