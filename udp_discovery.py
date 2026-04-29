"""
UDP 自動發現：監聽 9999 埠，收到 WHO_IS_SERVER 時回覆 SERVER_IP: <本機IP>
ESP32 開機後廣播此訊息即可找到伺服器。
"""

import socket
import threading
from typing import Callable, Optional

import config


def _get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def run_udp_listener(on_esp32_seen: Optional[Callable[[str], None]] = None) -> None:
    """
    在目前 thread 執行 UDP 監聽（阻塞）。
    on_esp32_seen: 收到 WHO_IS_SERVER 時以來源 IP 呼叫，供 StreamManager 記錄 ESP32 位址。
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("", config.UDP_PORT))
    sock.settimeout(1.0)

    my_ip = _get_local_ip()
    response = f"{config.UDP_RESPONSE_PREFIX}{my_ip}".encode()

    print(f"[UDP] Listening on port {config.UDP_PORT}, reply IP: {my_ip}")

    while True:
        try:
            data, addr = sock.recvfrom(256)
            try:
                msg = data.decode("utf-8").strip()
            except UnicodeDecodeError:
                msg = ""
            if getattr(config, "UDP_RECV_LOG", False):
                preview = (msg[:80] + "…") if len(msg) > 80 else msg
                print(
                    f"[UDP] recv {addr[0]}:{addr[1]} ({len(data)} B)"
                    f"{' -> ' + repr(preview) if preview else ' (binary/non-utf8)'}"
                )
            if not msg:
                continue
            if msg == config.UDP_DISCOVERY_MSG:
                sock.sendto(response, addr)
                print(f"[UDP] Replied to {addr[0]} -> SERVER_IP: {my_ip}")
                if on_esp32_seen:
                    on_esp32_seen(addr[0])
            elif getattr(config, "UDP_RECV_LOG", False):
                print(f"[UDP] ignore (not WHO_IS_SERVER) from {addr[0]}")
        except socket.timeout:
            continue
        except Exception as e:
            print(f"[UDP] Error: {e}")


def start_udp_listener_thread(on_esp32_seen: Optional[Callable[[str], None]] = None) -> threading.Thread:
    """啟動背景 thread 執行 UDP 監聽，回傳該 thread。"""
    t = threading.Thread(target=run_udp_listener, args=(on_esp32_seen,), daemon=True)
    t.start()
    return t
