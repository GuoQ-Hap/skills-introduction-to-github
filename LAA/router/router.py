from fastapi import FastAPI

from LAA.api.laaApi import router as laa_router


def init_router(app: FastAPI):
    app.include_router(laa_router, prefix="/laa", tags=["LAA"])
