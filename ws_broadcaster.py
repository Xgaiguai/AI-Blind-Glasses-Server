"""
WebSocket 連線管理（簡單版）。

目前我們採「每連線一個送出迴圈」的方式：
- ws/viewer：推送最新 JPEG
- ws_ui：推送監控狀態（JSON）
- ws：IMU 相容端點（接收 JSON 並回推 fusion snapshot）
"""

from __future__ import annotations

from typing import Set

from fastapi import WebSocket


viewer_clients: Set[WebSocket] = set()
ui_clients: Set[WebSocket] = set()
imu_clients: Set[WebSocket] = set()


def track_client(client_set: Set[WebSocket], ws: WebSocket) -> None:
    try:
        client_set.add(ws)
    except Exception:
        # WebSocket 物件在異常情況下可能無法加入集合；不致命
        pass


def untrack_client(client_set: Set[WebSocket], ws: WebSocket) -> None:
    try:
        client_set.discard(ws)
    except Exception:
        pass

