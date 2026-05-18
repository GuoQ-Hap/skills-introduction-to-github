"""后台管理系统 - 路由层"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from admin import service
from admin.model_pool import model_pool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/api")


# ─────── Pydantic 模型 ───────

class TestModelReq(BaseModel):
    provider: str
    prompt: str
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None

class ConfigSaveReq(BaseModel):
    items: List[Dict[str, str]]

class SqlExecReq(BaseModel):
    sql: str
    db_type: str = "mysql"

class PoolModelRef(BaseModel):
    provider: str
    model: str


# ─────── 仪表盘 ───────

@router.get("/dashboard")
def dashboard():
    return {
        "system": service.get_system_info(),
        "services": service.check_service_health(),
    }


# ─────── 配置管理 ───────

@router.get("/config/presets")
def config_presets():
    return service.get_config_presets()

@router.post("/config/save")
def config_save(req: ConfigSaveReq):
    return service.save_config_batch(req.items)


# ─────── 日志管理 ───────

@router.get("/logs/files")
def log_files():
    return service.list_log_files()

@router.get("/logs/read")
def log_read(filename: str, lines: int = 500, search: Optional[str] = None,
             level: Optional[str] = None, offset: int = 0):
    return service.read_log_file(filename, lines, search, level, offset)

@router.get("/logs/tail")
def log_tail(filename: str, n: int = 100):
    return service.tail_log_file(filename, n)

@router.post("/logs/level")
def log_level(level: str = Query(...)):
    ok = service.change_log_level(level)
    return {"success": ok}


# ─────── 模型管理 ───────

@router.get("/models/list")
def models_list():
    return service.list_models()

@router.get("/models/presets")
def models_presets():
    return service.get_model_presets()

@router.post("/models/test")
def models_test(req: TestModelReq):
    return service.test_model(req.provider, req.prompt, req.model, req.api_key, req.base_url)


# ─────── 数据库管理 ───────

@router.get("/db/connections")
def db_connections():
    return service.get_db_connections()

@router.get("/db/tables")
def db_tables(db_type: str = "mysql"):
    return service.get_mysql_tables(db_type)

@router.post("/db/execute")
def db_execute(req: SqlExecReq):
    return service.execute_admin_sql(req.sql, req.db_type)


# ─────── Milvus ───────

@router.get("/milvus/collections")
def milvus_collections():
    return service.list_milvus_collections()


# ─────── 路由列表 ───────

@router.get("/routes")
def api_routes(request: Request):
    return service.get_api_routes(request.app)


# ─────── 模型池管理 ───────

@router.get("/pool/status")
def pool_status():
    return model_pool.get_pool_status()

@router.get("/pool/models")
def pool_available_models():
    """返回已通过模型池验证的模型（主+备用）及最近全量测试时间；未验证的 .env 模型不会出现在 models 中。"""
    return model_pool.get_available_models_payload()

@router.post("/pool/test-all")
def pool_test_all():
    model_pool.run_full_test_async()
    return {"message": "全量测试已在后台启动"}

@router.post("/pool/retest")
def pool_retest(ref: PoolModelRef):
    return model_pool.retest_model(ref.provider, ref.model)

@router.post("/pool/set-primary")
def pool_set_primary(ref: PoolModelRef):
    ok = model_pool.set_primary(ref.provider, ref.model)
    return {"success": ok}

@router.post("/pool/add-standby")
def pool_add_standby(ref: PoolModelRef):
    ok = model_pool.add_to_standby(ref.provider, ref.model)
    return {"success": ok}

@router.post("/pool/remove-standby")
def pool_remove_standby(ref: PoolModelRef):
    ok = model_pool.remove_from_standby(ref.provider, ref.model)
    return {"success": ok}


# ─────── 记忆管理 ───────

@router.get("/memory/list")
def memory_list(module: Optional[str] = None, session_id: Optional[str] = None,
                keyword: Optional[str] = None,
                page: int = 1, page_size: int = 20):
    from Base.Service.memoryDbService import memory_db
    if keyword:
        return memory_db.search(keyword=keyword, module=module,
                                session_id=session_id, page=page, page_size=page_size)
    offset = (page - 1) * page_size
    return memory_db.list_all(module=module, session_id=session_id,
                              limit=page_size, offset=offset)

@router.get("/memory/stats")
def memory_stats():
    from Base.Service.memoryDbService import memory_db
    return memory_db.get_stats()

@router.get("/lsta/stats", summary="LSTA 业务统计（优化/点赞/差劲/评论）")
def lsta_stats():
    from Base.Service.memoryDbService import memory_db
    return memory_db.get_lsta_stats()

@router.get("/memory/sessions")
def memory_sessions(module: Optional[str] = None, page: int = 1, page_size: int = 20):
    from Base.Service.memoryDbService import memory_db
    return memory_db.get_sessions(module=module, page=page, page_size=page_size)

@router.get("/memory/search")
def memory_search(keyword: str, module: Optional[str] = None,
                  session_id: Optional[str] = None, intent: Optional[str] = None,
                  page: int = 1, page_size: int = 20):
    from Base.Service.memoryDbService import memory_db
    return memory_db.search(keyword=keyword, module=module,
                            session_id=session_id, intent=intent,
                            page=page, page_size=page_size)

@router.get("/memory/recall")
def memory_recall(query: str, module: Optional[str] = None,
                  session_id: Optional[str] = None, limit: int = 10):
    from Base.Service.memoryDbService import memory_db
    return memory_db.deep_recall(query=query, module=module or "all",
                                 session_id=session_id or "", limit=limit)

@router.get("/memory/detail/{memory_id}")
def memory_detail(memory_id: int):
    from Base.Service.memoryDbService import memory_db
    row = memory_db.get_by_id(memory_id)
    if row is None:
        return JSONResponse({"error": "not found"}, 404)
    return row

@router.delete("/memory/clear")
def memory_clear(module: str = Query(...), session_id: str = Query(...)):
    from Base.Service.memoryDbService import memory_db
    count = memory_db.clear_session(module=module, session_id=session_id)
    return {"deleted": count}


# ─────── 注册到 FastAPI ───────

def init_admin_router(app: FastAPI):
    from pathlib import Path
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/admin/static", StaticFiles(directory=str(static_dir)), name="admin-static")

    app.include_router(router)

    @app.get("/admin", response_class=HTMLResponse)
    @app.get("/admin/", response_class=HTMLResponse)
    def admin_index():
        html_file = static_dir / "index.html"
        if html_file.exists():
            return HTMLResponse(html_file.read_text(encoding="utf-8"))
        return HTMLResponse("<h1>Admin UI not found</h1>", status_code=404)

    logger.info("后台管理系统已挂载到 /admin")
