"""
Pydantic 模型：API 請求/回應
"""

from typing import Optional

from pydantic import BaseModel, Field  # type: ignore[import-untyped]


class GeminiTrigger(BaseModel):
    """POST /api/gemini 觸發場景分析（可選 body）"""
    mode: Optional[str] = Field(default="general", description="general | light | item_search")


class HealthResponse(BaseModel):
    status: str = "ok"
    server_ip: Optional[str] = None
