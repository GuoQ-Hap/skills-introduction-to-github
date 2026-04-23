from Base.Config.logConfig import setup_logging
setup_logging()

import logging

from fastapi import FastAPI

from admin.model_pool import model_pool
from LSTA.router.router import init_router

logger = logging.getLogger(__name__)

logger.info("启动自 LSTA 包")
app = FastAPI(title="LSTA - Amazon Listing 优化服务")
init_router(app=app)


@app.on_event("startup")
def on_startup():
    model_pool.run_full_test_async()
    logger.info("模型池全量测试已在后台启动")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app=app, host="0.0.0.0", port=8003)
