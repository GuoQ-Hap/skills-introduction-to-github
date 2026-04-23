import logging

from fastapi import FastAPI

from Base.Config.logConfig import setup_logging
from LMA.router.router import init_router

setup_logging()
logger = logging.getLogger(__name__)

logger.info("启动自 LMA 包")
app = FastAPI()
init_router(app=app)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app=app, host="0.0.0.0", port=8002)
