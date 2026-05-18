from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException

from LAA.core.laaCore import laa_engine
from LAA.models.laaState import LAAHealthResponse, LAAMatchRequest, LAAMatchResponse
from LAA.service.base import service_logger

logger = service_logger
router = APIRouter()


@router.get("/health", response_model=LAAHealthResponse, summary="LAA 健康检查")
def health():
    from admin.model_pool import model_pool

    primary = model_pool.primary
    model_name = f"{primary['provider']}:{primary['model']}" if primary else "none"
    return LAAHealthResponse(
        status="ok",
        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        model=model_name,
    )


@router.post("/match", response_model=LAAMatchResponse, summary="人群与场景最佳匹配")
def match(req: LAAMatchRequest):
    try:
        result, raw = laa_engine.match(req)
        return LAAMatchResponse(status="ok", result=result, raw_output=raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("LAA 匹配失败")
        raise HTTPException(status_code=500, detail=f"LAA 匹配失败: {e}")
