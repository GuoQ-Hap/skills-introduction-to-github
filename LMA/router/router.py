from fastapi import FastAPI

from LMA.api.coreApi import router as core_router


def init_router(app: FastAPI):
    app.include_router(core_router, prefix="/lma", tags=["LMA"])
