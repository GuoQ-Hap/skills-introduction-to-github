from Base.Config.logConfig import setup_logging
setup_logging()

import asyncio
import logging
import threading

from fastapi import FastAPI, Body

from Base.Client.mysqlClient import MySQLClient
# from auto_alarm.router.router import init_router as init_auto_alarm_router
from LMA.router.router import init_router as init_leang_router
from LMA.feishu import FeishuBot
from LDA.router.router import init_router as init_sti_router
from LDA.feishu import STIFeishuBot
from LSTA.router.router import init_router as init_listing_router
from LAA.router.router import init_router as init_laa_router
from admin.router import init_admin_router
from auth import init_auth_router
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

from version import APP_VERSION, APP_VERSION_FULL

app = FastAPI(
    title="LEANG AI 平台",
    version=APP_VERSION,
    description=f"LEANG AI 赋能平台 — {APP_VERSION_FULL}",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_auth_router(app=app)
init_leang_router(app=app)
init_sti_router(app=app)
init_listing_router(app=app)
init_laa_router(app=app)
# init_auto_alarm_router(app=app)
init_admin_router(app=app)

feishu_bot = FeishuBot()
sti_feishu_bot = STIFeishuBot()


def _start_feishu_bots():
    """在独立线程中用全新事件循环启动所有飞书 WebSocket 长连接。

    lark_oapi.ws.client 在模块级别缓存 event loop，无法在多线程中各自
    调用 start()。因此把所有 bot 放到同一个线程 + 同一个 event loop 中，
    直接调用 SDK 的异步方法来规避冲突。
    """
    import lark_oapi.ws.client as ws_mod

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    ws_mod.loop = loop

    bots: list[tuple[str, object]] = []
    if feishu_bot.app_id and feishu_bot.app_secret:
        feishu_bot.ws_client._lock = asyncio.Lock()
        bots.append(("leang", feishu_bot))
    if sti_feishu_bot.app_id and sti_feishu_bot.app_secret:
        sti_feishu_bot.ws_client._lock = asyncio.Lock()
        bots.append(("sti", sti_feishu_bot))

    if not bots:
        logger.warning("没有可用的飞书机器人配置，跳过 WebSocket 启动")
        return

    async def _run():
        for name, bot in bots:
            try:
                await bot.ws_client._connect()
                loop.create_task(bot.ws_client._ping_loop())
                logger.info("%s 飞书 WebSocket 长连接已建立", name)
            except Exception as e:
                logger.error("%s 飞书初始连接失败: %s", name, e)
                if bot.ws_client._auto_reconnect:
                    loop.create_task(bot.ws_client._reconnect())
        while True:
            await asyncio.sleep(3600)

    try:
        loop.run_until_complete(_run())
    except Exception:
        logger.exception("飞书 WebSocket 线程异常退出")


@app.on_event("startup")
def on_startup():
    try:
        t = threading.Thread(target=_start_feishu_bots, name="feishu-ws", daemon=True)
        t.start()
    except Exception:
        logger.exception("飞书 WebSocket 启动失败，跳过")

    try:
        from admin.model_pool import model_pool
        model_pool.run_full_test_async()
        logger.info("模型池全量测试已在后台启动")
    except Exception:
        logger.exception("模型池测试启动失败，跳过")


@app.post("/execute_sql")
def read_root(sql: str = Body(..., embed=True)):
    result = MySQLClient().execute_sync(sql)
    return result


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app="main:app", host="0.0.0.0", port=8000)