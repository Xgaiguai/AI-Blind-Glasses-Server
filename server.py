#!/usr/bin/env python3
"""
AI 智慧導盲眼鏡 - 測試伺服器
提供 UDP 探索、API 端點、TTS 音檔，與 ESP32 韌體對接。
"""

import socket
import threading
import os
import json
import time
from pathlib import Path
from datetime import datetime

from flask import Flask, request, Response  # type: ignore[import-untyped]

import config
from audio_utils import generate_tts, set_latest_audio, get_latest_audio

app = Flask(__name__)

# 建立資料目錄
Path(config.DATA_DIR).mkdir(exist_ok=True)

# 記錄最後收到的 ESP32 IP（來自 UDP 或 HTTP 請求）
_last_esp32_ip: str | None = None


def get_local_ip() -> str:
    """取得本機對外 IP（用於回覆 UDP 探索）"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def udp_listener():
    """UDP 探索：收到 WHO_IS_SERVER 時回覆 SERVER_IP"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("", config.UDP_PORT))
    sock.settimeout(1.0)

    my_ip = get_local_ip()
    response = f"{config.UDP_RESPONSE_PREFIX}{my_ip}".encode()

    print(f"[UDP] 監聽 port {config.UDP_PORT}，回覆 IP: {my_ip}")

    while True:
        try:
            data, addr = sock.recvfrom(256)
            msg = data.decode().strip()
            if msg == config.UDP_DISCOVERY_MSG:
                sock.sendto(response, addr)
                print(f"[UDP] 回覆 {addr[0]} -> SERVER_IP: {my_ip}")
                global _last_esp32_ip
                _last_esp32_ip = addr[0]
        except socket.timeout:
            continue
        except Exception as e:
            print(f"[UDP] 錯誤: {e}")


def _log_request(tag: str, data: str | bytes | dict | None = None):
    if not config.LOG_REQUESTS:
        return
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    client = request.remote_addr if request else "?"
    msg = f"[{ts}] {tag} from {client}"
    if data is not None:
        if isinstance(data, (dict, str)):
            msg += f" | {data}"
        elif isinstance(data, bytes) and len(data) < 200:
            msg += f" | {data[:100]}..."
    print(msg)


# ---------- API 端點 ----------


@app.route("/api/gemini", methods=["POST", "GET"])
def api_gemini():
    """風景 / 紅綠燈 / 物品查找"""
    mode = request.args.get("mode", "general")
    global _last_esp32_ip
    _last_esp32_ip = request.remote_addr

    _log_request("GEMINI", {"mode": mode})

    # 產生對應 TTS 並快取
    texts = {
        "general": "這是風景模式，辨識完成",
        "light": "紅綠燈辨識完成",
        "item_search": "物品查找完成",
    }
    text = texts.get(mode, "已收到請求")
    try:
        audio_data, content_type = generate_tts(text)
        set_latest_audio(audio_data, content_type)
    except Exception as e:
        _log_request("GEMINI TTS", str(e))

    return {"ok": True, "mode": mode}, 200


@app.route("/api/asr", methods=["POST"])
def api_asr():
    """語音指令：接收 WAV，回寫 TTS"""
    global _last_esp32_ip
    _last_esp32_ip = request.remote_addr

    data = request.get_data()
    _log_request("ASR", f"WAV {len(data)} bytes")

    # 可在此接 Whisper 等 ASR，目前產生固定回覆
    out_dir = Path(config.DATA_DIR)
    out_dir.mkdir(exist_ok=True)
    wav_path = out_dir / f"asr_{int(time.time())}.wav"
    with open(wav_path, "wb") as f:
        f.write(data)

    try:
        audio_data, content_type = generate_tts("已收到語音指令")
        set_latest_audio(audio_data, content_type)
    except Exception as e:
        _log_request("ASR TTS", str(e))

    return {"ok": True}, 200


@app.route("/api/imu", methods=["POST"])
def api_imu():
    """IMU 資料"""
    global _last_esp32_ip
    _last_esp32_ip = request.remote_addr

    try:
        j = request.get_json()
        _log_request("IMU", j)
        if config.LOG_REQUESTS:
            out = Path(config.DATA_DIR) / "imu_log.txt"
            with open(out, "a") as f:
                f.write(f"{datetime.now().isoformat()} {json.dumps(j)}\n")
    except Exception:
        pass
    return {"ok": True}, 200


@app.route("/api/gps", methods=["POST"])
def api_gps():
    """GPS 資料"""
    global _last_esp32_ip
    _last_esp32_ip = request.remote_addr

    try:
        j = request.get_json()
        _log_request("GPS", j)
        if config.LOG_REQUESTS:
            out = Path(config.DATA_DIR) / "gps_log.txt"
            with open(out, "a") as f:
                f.write(f"{datetime.now().isoformat()} {json.dumps(j)}\n")
    except Exception:
        pass
    return {"ok": True}, 200


@app.route("/audio/latest", methods=["GET"])
def audio_latest():
    """回傳最新 TTS 音檔"""
    data, content_type = get_latest_audio()
    return Response(data, mimetype=content_type)


@app.route("/health", methods=["GET"])
def health():
    """健康檢查"""
    return {"status": "ok", "server_ip": get_local_ip()}, 200


def main():
    # 背景執行 UDP 監聽
    t = threading.Thread(target=udp_listener, daemon=True)
    t.start()

    # 預設 TTS
    try:
        audio_data, content_type = generate_tts("伺服器已就緒")
        set_latest_audio(audio_data, content_type)
    except Exception:
        set_latest_audio(b"", "audio/wav")  # 會用 fallback

    print(f"\n=== AI 智慧導盲眼鏡 - 測試伺服器 ===")
    print(f"  HTTP: http://{get_local_ip()}:{config.HTTP_PORT}")
    print(f"  UDP 探索: port {config.UDP_PORT}")
    print(f"  ESP32 請與本機同一 WiFi\n")

    app.run(host=config.HTTP_HOST, port=config.HTTP_PORT, debug=False, threaded=True)


if __name__ == "__main__":
    main()
