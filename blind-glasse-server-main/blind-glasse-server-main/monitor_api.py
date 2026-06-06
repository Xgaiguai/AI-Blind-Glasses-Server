"""
監控 API router：
- /api/monitor/state
- /api/monitor/events
- /api/monitor/frame
"""

import hashlib
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response


def create_monitor_router(
    get_state_fn: Callable[[], Dict[str, Any]],
    get_events_fn: Callable[[int], List[Dict[str, Any]]],
    get_frame_fn: Callable[[], Optional[bytes]],
    get_health_fn: Optional[Callable[[], Dict[str, Any]]] = None,
    get_latency_fn: Optional[Callable[[], Dict[str, Any]]] = None,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/monitor/state")
    async def monitor_state() -> Dict[str, Any]:
        return get_state_fn()

    @router.get("/api/monitor/events")
    async def monitor_events(limit: int = 30) -> Dict[str, Any]:
        limit = max(1, min(200, int(limit)))
        return {"events": get_events_fn(limit)}

    @router.get("/api/monitor/frame")
    async def monitor_frame(request: Request):
        frame = get_frame_fn()
        if not frame:
            # 無串流幀：用 204 表示「暫無內容」，避免監控頁每秒輪詢刷 404 日誌
            return Response(status_code=204)
        etag = f'W/"{hashlib.md5(frame).hexdigest()}"'
        inm = request.headers.get("if-none-match")
        if inm and inm.strip() == etag:
            return Response(
                status_code=304,
                headers={
                    "ETag": etag,
                    "Cache-Control": "private, max-age=0, must-revalidate",
                },
            )
        return Response(
            content=frame,
            media_type="image/jpeg",
            headers={
                "ETag": etag,
                "Cache-Control": "private, max-age=0, must-revalidate",
            },
        )

    @router.get("/api/monitor/health")
    async def monitor_health() -> Dict[str, Any]:
        if get_health_fn is not None:
            return get_health_fn()
        return {"status": "ok"}

    @router.get("/api/monitor/latency")
    async def monitor_latency() -> Dict[str, Any]:
        if get_latency_fn is not None:
            return get_latency_fn()
        return {"stats": {}, "recent": []}

    return router

