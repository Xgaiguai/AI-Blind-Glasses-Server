"""
核心告警與家屬通知測試（簡化版）
執行：
  cd server
  python test_core_alerts.py
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest import mock

import config
from fastapi.testclient import TestClient

import gemini_pool
from event_engine import EventEngine
from fall_detector import FallDetector
from line_notifier import LineNotifier
from main import app


def _assert(ok: bool, msg: str) -> None:
    if not ok:
        raise AssertionError(msg)


def test_fall_detector_basic() -> None:
    d = FallDetector()
    d.threshold = 10
    d.confirm_sec = 0.0
    d.cooldown_sec = 9999
    out1 = d.update({"gz": 20})
    _assert(out1["triggered"] is True, "fall should trigger")
    out2 = d.update({"gz": 20})
    _assert(out2["triggered"] is False, "fall should be throttled by cooldown")


def test_event_engine_map_and_emergency() -> None:
    e = EventEngine()
    e.update_gps({"lat": 25.03, "lng": 121.56, "sat": 7})
    snap = e.get_snapshot()
    _assert("maps.google.com" in (snap["last_gps"]["map_url"] or ""), "map url missing")
    em = e.emergency_event("btn")
    _assert(em["type"] == "emergency", "emergency event type mismatch")


def test_gemini_pool_round_robin() -> None:
    old_k1 = config.GEMINI_API_KEY_1
    old_k2 = config.GEMINI_API_KEY_2
    old_legacy = config.GEMINI_API_KEY
    config.GEMINI_API_KEY_1 = "k1"
    config.GEMINI_API_KEY_2 = "k2"
    config.GEMINI_API_KEY = ""

    class _FakeModel:
        def __init__(self, key: str):
            self.key = key

        def generate_content(self, _parts):
            return SimpleNamespace(text=self.key)

    class _FakeGenAI:
        last_key = ""

        @staticmethod
        def configure(api_key: str):
            _FakeGenAI.last_key = api_key

        @staticmethod
        def GenerativeModel(_name: str):
            return _FakeModel(_FakeGenAI.last_key)

    old_has = gemini_pool._HAS_GEMINI
    old_genai = gemini_pool.genai
    gemini_pool._HAS_GEMINI = True
    gemini_pool.genai = _FakeGenAI
    try:
        r1 = gemini_pool.call_with_pool(lambda m: m.generate_content(["x"]).text)
        r2 = gemini_pool.call_with_pool(lambda m: m.generate_content(["x"]).text)
        _assert(r1 in ("k1", "k2"), "pool first key invalid")
        _assert(r2 in ("k1", "k2") and r2 != r1, "pool not rotating")
    finally:
        gemini_pool._HAS_GEMINI = old_has
        gemini_pool.genai = old_genai
        config.GEMINI_API_KEY_1 = old_k1
        config.GEMINI_API_KEY_2 = old_k2
        config.GEMINI_API_KEY = old_legacy


def test_line_notifier_payload() -> None:
    old_enable = config.LINE_NOTIFY_ENABLE
    old_token = config.LINE_CHANNEL_ACCESS_TOKEN
    old_targets = config.LINE_TARGET_IDS
    config.LINE_NOTIFY_ENABLE = True
    config.LINE_CHANNEL_ACCESS_TOKEN = "token"
    config.LINE_TARGET_IDS = "U123"
    n = LineNotifier()
    with mock.patch("line_notifier.requests.post") as post:
        post.return_value.status_code = 200
        r = n.push_text("hello")
        _assert(r["ok"] is True, "line push text failed")
        _assert(post.call_count == 1, "line push call count mismatch")
    config.LINE_NOTIFY_ENABLE = old_enable
    config.LINE_CHANNEL_ACCESS_TOKEN = old_token
    config.LINE_TARGET_IDS = old_targets


def test_family_status_api() -> None:
    c = TestClient(app)
    r = c.get("/api/family/status")
    _assert(r.status_code == 200, "family status api failed")
    body = r.json()
    _assert(body.get("ok") is True, "family status body invalid")


def test_imu_post_updates_monitor_state_fusion() -> None:
    """POST /api/imu 應更新 fusion，監控頁輪詢 /api/monitor/state 才會看到六軸數字。"""
    c = TestClient(app)
    r = c.post(
        "/api/imu",
        json={"ax": 0.12, "ay": -0.05, "az": 0.98, "gx": 0.1, "gy": 0.2, "gz": -0.3},
    )
    _assert(r.status_code == 200, f"imu post failed {r.status_code}")
    st = c.get("/api/monitor/state").json()
    fus = st.get("fusion") or {}
    _assert(fus.get("ax") is not None, "fusion ax missing after imu post")
    _assert(fus.get("gz") is not None, "fusion gz missing after imu post")
    _assert(isinstance(fus.get("last_imu_sample"), dict), "last_imu_sample should be dict")
    _assert("ax" in fus["last_imu_sample"], "last_imu_sample should echo keys")


def test_line_webhook_location_command() -> None:
    c = TestClient(app)
    with mock.patch("main._line_notifier.reply_text") as reply:
        reply.return_value = {"ok": True}
        old_secret = config.LINE_CHANNEL_SECRET
        config.LINE_CHANNEL_SECRET = ""
        try:
            payload = {
                "events": [
                    {
                        "type": "message",
                        "replyToken": "token123",
                        "message": {"type": "text", "text": "位置"},
                    }
                ]
            }
            r = c.post("/api/line/webhook", json=payload)
            _assert(r.status_code == 200, "line webhook failed")
            _assert(reply.call_count == 1, "line webhook reply not called")
        finally:
            config.LINE_CHANNEL_SECRET = old_secret


def run() -> None:
    start = time.time()
    test_fall_detector_basic()
    test_event_engine_map_and_emergency()
    test_gemini_pool_round_robin()
    test_line_notifier_payload()
    test_family_status_api()
    test_imu_post_updates_monitor_state_fusion()
    test_line_webhook_location_command()
    print(f"OK: core alerts tests passed in {time.time()-start:.2f}s")


if __name__ == "__main__":
    run()

