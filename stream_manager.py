"""
管理 ESP32 MJPEG 串流：由伺服器主動拉取 ESP32 的 /stream，維護最新一幀（thread-safe）。
"""

import re
import socket
import threading
import time
from typing import Optional, Tuple

import requests  # type: ignore[import-untyped]
from requests.adapters import HTTPAdapter  # type: ignore[import-untyped]
from urllib3.util.retry import Retry  # type: ignore[import-untyped]

import config


class StreamManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest_frame: Optional[bytes] = None
        self._latest_ts: float = 0.0
        self._esp32_ip: Optional[str] = None
        self._puller_thread: Optional[threading.Thread] = None
        self._puller_stop = threading.Event()
        self._frame_timeout_sec = getattr(
            config, "STREAM_FRAME_TIMEOUT_SEC", 3.0
        )

    def set_esp32_ip(self, ip: str) -> None:
        """設定 ESP32 IP（由 UDP 發現或首次請求取得），並啟動拉流（若尚未啟動）。"""
        with self._lock:
            if ip == self._esp32_ip:
                return
            self._esp32_ip = ip
        self._stop_puller()
        self._start_puller(ip)

    def get_esp32_ip(self) -> Optional[str]:
        with self._lock:
            return self._esp32_ip

    def set_frame(self, data: bytes) -> None:
        """更新最新一幀（thread-safe）。"""
        with self._lock:
            self._latest_frame = data
            self._latest_ts = time.time()

    def get_latest_frame(self) -> Tuple[Optional[bytes], float]:
        """回傳 (最新幀 bytes, 時間戳)；若無則 (None, 0)。"""
        with self._lock:
            if self._latest_frame is None:
                return None, 0.0
            return self._latest_frame, self._latest_ts

    def has_recent_frame(self) -> bool:
        """是否在 timeout 內收到過 frame。"""
        with self._lock:
            if self._latest_frame is None:
                return False
            return (time.time() - self._latest_ts) <= self._frame_timeout_sec

    def _start_puller(self, esp32_ip: str) -> None:
        def run() -> None:
            url = f"http://{esp32_ip}:{config.ESP32_STREAM_PORT}{config.ESP32_STREAM_PATH}"
            boundary = b"frame"
            buf = b""
            while not self._puller_stop.is_set():
                r = None
                try:
                    session = requests.Session()
                    retries = Retry(total=3, backoff_factor=0.5)
                    session.mount("http://", HTTPAdapter(max_retries=retries))
                    r = session.get(url, stream=True, timeout=5)
                    r.raise_for_status()
                    ct = r.headers.get("Content-Type", "")
                    m = re.search(r'boundary=([^;\s]+)', ct)
                    if m:
                        boundary = m.group(1).strip().encode()
                    for chunk in r.iter_content(chunk_size=8192):
                        if self._puller_stop.is_set():
                            break
                        buf += chunk
                        while True:
                            start = b"--" + boundary + b"\r\n"
                            idx = buf.find(start)
                            if idx == -1:
                                if len(buf) > 1024 * 1024:
                                    buf = buf[-512 * 1024:]
                                break
                            rest = buf[idx + len(start):]
                            end = rest.find(b"\r\n\r\n")
                            if end == -1:
                                break
                            headers = rest[:end].decode("utf-8", errors="ignore")
                            body_start = end + 4
                            cl = None
                            if "Content-Length:" in headers:
                                try:
                                    m = re.search(r"Content-Length:\s*(\d+)", headers)
                                    if m is not None:
                                        cl = int(m.group(1))
                                except (AttributeError, ValueError):
                                    pass
                            if cl is not None:
                                if len(rest) >= body_start + cl:
                                    jpg = rest[body_start:body_start + cl]
                                    buf = rest[body_start + cl:]
                                    self.set_frame(jpg)
                                else:
                                    buf = buf[idx:]
                                    break
                            else:
                                buf = rest[body_start:]
                            break
                except (requests.RequestException, OSError) as e:
                    if not self._puller_stop.is_set():
                        print(f"[Stream] Pull error: {e}")
                finally:
                    try:
                        if r is not None:
                            r.close()
                    except Exception:
                        pass
                if not self._puller_stop.is_set():
                    time.sleep(1)

        self._puller_stop.clear()
        self._puller_thread = threading.Thread(target=run, daemon=True)
        self._puller_thread.start()
        print(f"[Stream] Puller started for {esp32_ip}")

    def _stop_puller(self) -> None:
        self._puller_stop.set()
        if self._puller_thread:
            self._puller_thread.join(timeout=2)
            self._puller_thread = None


# 單例，供 FastAPI 與其他模組使用
stream_manager = StreamManager()
