"""
伺服器功能測試：驗證主要 API 是否正常。
執行：在 server 目錄下 python test_server.py
"""

import sys
from io import BytesIO

# 最小 WAV 檔頭 + 一點靜音（約 0.1 秒），供 /api/asr 測試
def make_minimal_wav():
    import wave
    buf = BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 800)
    buf.seek(0)
    return buf.read()


def run_tests():
    from fastapi.testclient import TestClient
    from main import app, _get_last_gps
    import config

    client = TestClient(app)
    results = []

    # 1. 健康檢查
    try:
        r = client.get("/health")
        ok = r.status_code == 200 and r.json().get("status") == "ok"
        results.append(("GET /health", ok, r.status_code, r.json() if ok else r.text[:200]))
    except Exception as e:
        results.append(("GET /health", False, None, str(e)))

    # 2. 根路徑
    try:
        r = client.get("/")
        ok = r.status_code == 200
        results.append(("GET /", ok, r.status_code, r.text[:80] if ok else r.text[:200]))
    except Exception as e:
        results.append(("GET /", False, None, str(e)))

    # 3. 上傳 GPS（導航起點）
    try:
        r = client.post("/api/gps", json={"lat": 25.0330, "lng": 121.5654})
        ok = r.status_code == 200 and r.json().get("ok") is True
        results.append(("POST /api/gps", ok, r.status_code, r.json() if ok else r.text[:200]))
    except Exception as e:
        results.append(("POST /api/gps", False, None, str(e)))

    # 4. 驗證 GPS 已儲存（供導航用）
    try:
        gps = _get_last_gps(config.LAST_GPS_MAX_AGE_SEC)
        ok = gps is not None and gps.get("lat") == 25.0330 and gps.get("lng") == 121.5654
        results.append(("GPS 已儲存 (導航起點)", ok, None, str(gps) if gps else "None"))
    except Exception as e:
        results.append(("GPS 已儲存", False, None, str(e)))

    # 5. 語音 ASR（送最小 WAV，預期辨識為「其他」）
    try:
        wav = make_minimal_wav()
        r = client.post("/api/asr", content=wav, headers={"Content-Type": "audio/wav"})
        ok = r.status_code == 200 and r.json().get("ok") is True
        results.append(("POST /api/asr", ok, r.status_code, r.json() if ok else r.text[:200]))
    except Exception as e:
        results.append(("POST /api/asr", False, None, str(e)))

    # 6. 避障 API
    try:
        r = client.get("/api/obstacle")
        ok = r.status_code == 200 and "obstacle" in r.json()
        results.append(("GET /api/obstacle", ok, r.status_code, r.json() if ok else r.text[:200]))
    except Exception as e:
        results.append(("GET /api/obstacle", False, None, str(e)))

    # 7. 監控 state
    try:
        r = client.get("/api/monitor/state")
        body = r.json() if r.status_code == 200 else {}
        ok = r.status_code == 200 and "mode" in body and "navigation" in body
        results.append(("GET /api/monitor/state", ok, r.status_code, body if ok else r.text[:200]))
    except Exception as e:
        results.append(("GET /api/monitor/state", False, None, str(e)))

    # 8. 監控 events
    try:
        r = client.get("/api/monitor/events?limit=5")
        body = r.json() if r.status_code == 200 else {}
        ok = r.status_code == 200 and "events" in body
        results.append(("GET /api/monitor/events", ok, r.status_code, body if ok else r.text[:200]))
    except Exception as e:
        results.append(("GET /api/monitor/events", False, None, str(e)))

    # 9. 音訊最新（可能 404 若尚未有 TTS）
    try:
        r = client.get("/audio/latest")
        ok = r.status_code in (200, 404)
        results.append(("GET /audio/latest", ok, r.status_code, "OK" if r.status_code == 200 else "no_audio (正常)"))
    except Exception as e:
        results.append(("GET /audio/latest", False, None, str(e)))

    return results


if __name__ == "__main__":
    print("正在載入伺服器模組並執行測試…\n")
    try:
        results = run_tests()
    except Exception as e:
        print(f"載入失敗: {e}")
        sys.exit(1)

    failed = 0
    for name, ok, code, detail in results:
        status = "通過" if ok else "失敗"
        if not ok:
            failed += 1
        code_str = f" [{code}]" if code is not None else ""
        print(f"  {name}{code_str}: {status}")
        if not ok or isinstance(detail, dict):
            print(f"    -> {detail}")

    print()
    if failed == 0:
        print("全部測試通過，伺服器功能正常。")
        sys.exit(0)
    else:
        print(f"有 {failed} 項失敗。")
        sys.exit(1)
