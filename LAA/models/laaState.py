from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


class LAAMatchRequest(BaseModel):
    image_url: Optional[str] = Field(None, description="商品图片 URL")
    image_base64: Optional[str] = Field(
        None,
        description="图片 base64 内容。可直接传纯 base64，或完整 data:image/...;base64,...",
    )
    comment: str = Field(..., min_length=1, description="用户评论或商品描述文本")
    color: str = Field(..., min_length=1, description="颜色信息")
    size: str = Field(..., min_length=1, description="尺寸信息")
    model: Optional[str] = Field(None, description="可选，指定模型 provider:model")

    @model_validator(mode="after")
    def validate_image_input(self):
        if not (self.image_url or self.image_base64):
            raise ValueError("image_url 和 image_base64 至少传一个")
        return self


class LAACandidate(BaseModel):
    name: str = ""
    reason: str = ""
    score: int = 0


class LAAMatchResult(BaseModel):
    best_audience: str = ""
    best_scene: str = ""
    audience_candidates: List[LAACandidate] = Field(default_factory=list)
    scene_candidates: List[LAACandidate] = Field(default_factory=list)
    best_selling_point: str = ""
    best_selling_point_reason: str = ""
    best_selling_point_score: int = 0
    best_selling_point_candidates: List[LAACandidate] = Field(default_factory=list)
    insight: str = ""


class LAAMatchResponse(BaseModel):
    status: str = "ok"
    result: LAAMatchResult
    raw_output: str = ""


class LAAHealthResponse(BaseModel):
    status: str = "ok"
    time: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    model: str = "none"
