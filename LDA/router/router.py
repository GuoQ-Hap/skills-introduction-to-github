from fastapi import FastAPI

from LDA.api.sqlApi import router as sql_router


def init_router(app: FastAPI):
    app.include_router(sql_router, prefix="/lda", tags=["LDA"])
