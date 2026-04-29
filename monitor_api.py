"""
監控 API router：
- /api/monitor/state
- /api/monitor/events
- /api/monitor/frame
"""

from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response


def create_monitor_router(
    get_state_fn: Callable[[], Dict[str, Any]],
    get_events_fn: Callable[[int], List[Dict[str, Any]]],
    get_frame_fn: Callable[[], Optional[bytes]],
    get_health_fn: Optional[Callable[[], Dict[str, Any]]] = None,
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
    async def monitor_frame():
        frame = get_frame_fn()
        if not frame:
            # 無串流幀：用 204 表示「暫無內容」，避免監控頁每秒輪詢刷 404 日誌
            return Response(status_code=204)
        return Response(content=frame, media_type="image/jpeg")

    @router.get("/api/monitor/health")
    async def monitor_health() -> Dict[str, Any]:
        if get_health_fn is not None:
            return get_health_fn()
        return {"status": "ok"}

    return router

