from fastapi import FastAPI

from LSTA.api.listingApi import router as listing_router


def init_router(app: FastAPI):
    app.include_router(listing_router, prefix="/lsta", tags=["LSTA"])
