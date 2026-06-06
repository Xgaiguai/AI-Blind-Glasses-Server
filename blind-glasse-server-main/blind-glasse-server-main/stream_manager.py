"""
管理 ESP32 MJPEG 串流：由伺服器主動拉取 ESP32 的 /stream，維護最新一幀（thread-safe）。
"""

import re
import socket
import threading
import time
from typing import Optional, Tuple
from urllib.parse import urlparse

import requests  # type: ignore[import-untyped]
from requests.adapters import HTTPAdapter  # type: ignore[import-untyped]
from urllib3.util.retry import Retry  # type: ignore[import-untyped]

import config


def _format_host_for_url(host: str) -> str:
    """
    URL host formatting:
    - IPv4 / domain: 그대로
    - IPv6: wrap with []
    """
    h = (host or "").strip()
    if not h:
        return h
    # Already bracketed IPv6
    if h.startswith("[") and h.endswith("]"):
        return h
    # If host contains ":" it's likely IPv6 literal
    if ":" in h:
        return f"[{h}]"
    return h


class StreamManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest_frame: Optional[bytes] = None
        self._latest_ts: float = 0.0
        self._esp32_ip: Optional[str] = None
        # 韌體經 X-Device-Stream-Url 回報的 MJPEG 完整 URL（雲端反代後勿再用 client IP 組 :81/stream）
        self._device_pull_url: Optional[str] = None
        self._puller_thread: Optional[threading.Thread] = None
        self._puller_stop = threading.Event()
        self._frame_timeout_sec = getattr(
            config, "STREAM_FRAME_TIMEOUT_SEC", 3.0
        )
        self._last_pull_err_log_ts: float = 0.0
        # 供關閉時 close()，盡快打斷 iter_content 阻塞，讓 uvicorn 不必卡太久
        self._active_response: Optional[object] = None

    @staticmethod
    def _url_is_recursive_public_stream(url: str) -> bool:
        """勿拉取本站對外 /stream，否則經隧道打回自己，逾時與 502 循環。"""
        try:
            p = urlparse((url or "").strip())
            h = (p.hostname or "").lower()
            path = (p.path or "").lower()
            if "/stream" not in path:
                return False
            port = p.port
            if p.scheme == "https" and port is None:
                port = 443
            elif p.scheme == "http" and port is None:
                port = 80
            http_app = int(getattr(config, "HTTP_PORT", 5000))
            if h == "blind-glasses.org" and port in (80, 443):
                return True
            if h in ("localhost", "127.0.0.1", "::1") and port == http_app:
                return True
            return False
        except Exception:
            return False

    def set_esp32_ip(self, ip: str) -> None:
        """設定 ESP32 IP（由 UDP 發現或首次請求取得），並啟動拉流（若尚未啟動）。"""
        with self._lock:
            if self._device_pull_url:
                return
            if ip == self._esp32_ip:
                return
            self._esp32_ip = ip
        self._stop_puller()
        self._start_puller(ip)

    def get_esp32_ip(self) -> Optional[str]:
        with self._lock:
            return self._esp32_ip

    def get_device_pull_url(self) -> Optional[str]:
        with self._lock:
            return self._device_pull_url

    def set_device_pull_url(self, url: Optional[str]) -> None:
        """由裝置 HTTP Header 設定要拉的 MJPEG URL；None 或空字串表示清除。"""
        u = (url or "").strip()
        if u and self._url_is_recursive_public_stream(u):
            print(
                "[Stream] Ignored X-Device-Stream-Url pointing at this site's /stream "
                "(use http://<esp32-lan>:81/stream or a tunnel to the camera)."
            )
            u = None
        if not u:
            u = None
        with self._lock:
            if u == self._device_pull_url:
                return
            self._device_pull_url = u
            esp = self._esp32_ip
        self._stop_puller()
        if u:
            self._start_puller("device-stream")
        elif esp:
            self._start_puller(esp)
        elif (getattr(config, "ESP32_STREAM_URL", "") or "").strip():
            self._start_puller("esp32-stream-url")

    def _effective_pull_url(self, esp32_ip: str) -> str:
        with self._lock:
            if self._device_pull_url:
                return self._device_pull_url
        env_url = (getattr(config, "ESP32_STREAM_URL", "") or "").strip()
        if env_url:
            return env_url
        host = _format_host_for_url(esp32_ip)
        return f"http://{host}:{config.ESP32_STREAM_PORT}{config.ESP32_STREAM_PATH}"

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
            url = self._effective_pull_url(esp32_ip)
            print(f"[Stream] Pulling MJPEG from {url!r}")
            connect_t = float(getattr(config, "STREAM_PULL_CONNECT_TIMEOUT_SEC", 3.0))
            read_t = float(getattr(config, "STREAM_PULL_READ_TIMEOUT_SEC", 25.0))
            pull_timeout = (connect_t, read_t)
            retry_sleep = max(0.05, float(getattr(config, "STREAM_PULL_RETRY_SLEEP_SEC", 0.25)))
            boundary = b"frame"
            buf = b""
            while not self._puller_stop.is_set():
                r = None
                try:
                    session = requests.Session()
                    retries = Retry(total=3, backoff_factor=0.5)
                    adapter = HTTPAdapter(max_retries=retries)
                    session.mount("http://", adapter)
                    session.mount("https://", adapter)
                    r = session.get(url, stream=True, timeout=pull_timeout)
                    r.raise_for_status()
                    with self._lock:
                        self._active_response = r
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
                            # 在邊界後有限範圍內找 Content-Length（相容：單一 header 區塊，或舊韌體分兩段送）
                            head_scan = rest[: min(len(rest), 65536)]
                            mlen = re.search(rb"Content-Length:\s*(\d+)", head_scan)
                            if mlen is None:
                                if len(rest) > 65536:
                                    buf = buf[idx + 2:]
                                break
                            try:
                                cl = int(mlen.group(1))
                            except ValueError:
                                buf = buf[idx + 2:]
                                break
                            end_hdr = rest.find(b"\r\n\r\n", mlen.start())
                            if end_hdr == -1:
                                break
                            body_start = end_hdr + 4
                            if cl < 0 or len(rest) < body_start + cl:
                                buf = buf[idx:]
                                break
                            jpg = rest[body_start : body_start + cl]
                            buf = rest[body_start + cl :]
                            self.set_frame(jpg)
                            continue
                except (requests.RequestException, OSError) as e:
                    if not self._puller_stop.is_set():
                        now = time.time()
                        if now - self._last_pull_err_log_ts >= 15.0:
                            print(f"[Stream] Pull error: {e}")
                            self._last_pull_err_log_ts = now
                finally:
                    try:
                        if r is not None:
                            r.close()
                    except Exception:
                        pass
                    with self._lock:
                        if self._active_response is r:
                            self._active_response = None
                if not self._puller_stop.is_set():
                    time.sleep(retry_sleep)

        self._puller_stop.clear()
        self._puller_thread = threading.Thread(target=run, daemon=True)
        self._puller_thread.start()
        print(f"[Stream] Puller started for {esp32_ip}")

    def _stop_puller(self) -> None:
        self._puller_stop.set()
        with self._lock:
            ar = self._active_response
            self._active_response = None
        if ar is not None:
            try:
                ar.close()
            except Exception:
                pass
        if self._puller_thread:
            self._puller_thread.join(timeout=4)
            self._puller_thread = None

    def shutdown_for_exit(self) -> None:
        """應用程式關閉時呼叫：打斷拉流，減少 uvicorn 卡在 Waiting for connections。"""
        self._stop_puller()


# 單例，供 FastAPI 與其他模組使用
stream_manager = StreamManager()
