"""sql_to_index 飞书长连接机器人 — 数据查询助手。"""
from __future__ import annotations

import json
import logging
import threading
from typing import Dict

import lark_oapi as lark
from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody

from LDA.constants import STI_FEISHU_APP_ID, STI_FEISHU_APP_SECRET
from LDA.core.sqlCore import LLMNLPtoSQL

logger = logging.getLogger(__name__)

_engine_lock = threading.Lock()
_sessions: Dict[str, LLMNLPtoSQL] = {}
MAX_SESSIONS = 200


def _feishu_memory_session_id(user_id: str) -> str:
    return f"sti-feishu-{user_id}"


def _get_engine(user_id: str) -> LLMNLPtoSQL:
    with _engine_lock:
        if user_id in _sessions:
            return _sessions[user_id]
        if len(_sessions) >= MAX_SESSIONS:
            oldest = next(iter(_sessions))
            del _sessions[oldest]
        engine = LLMNLPtoSQL()
        engine.hydrate_from_db(_feishu_memory_session_id(user_id))
        _sessions[user_id] = engine
        return engine


class STIFeishuBot:
    """sql_to_index 飞书长连接机器人。

    每个飞书用户独立会话记忆，通过 LLMNLPtoSQL 处理数据查询。
    """

    def __init__(self):
        self.app_id = STI_FEISHU_APP_ID
        self.app_secret = STI_FEISHU_APP_SECRET

        if not self.app_id or not self.app_secret:
            logger.warning("STI_FEISHU_APP_ID / STI_FEISHU_APP_SECRET 未配置")

        self.api_client = (
            lark.Client.builder()
            .app_id(self.app_id)
            .app_secret(self.app_secret)
            .log_level(lark.LogLevel.INFO)
            .build()
        )

        event_handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._on_message)
            .build()
        )
        self.ws_client = lark.ws.Client(
            self.app_id,
            self.app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO,
        )

    def _on_message(self, data: lark.im.v1.P2ImMessageReceiveV1) -> None:
        t = threading.Thread(target=self._handle, args=(data,), daemon=True)
        t.start()

    def _handle(self, data: lark.im.v1.P2ImMessageReceiveV1) -> None:
        try:
            msg = data.event.message
            sender = data.event.sender
            message_id = msg.message_id
            user_id = sender.sender_id.open_id if sender.sender_id else "unknown"

            if msg.message_type != "text":
                self._reply(message_id, "目前只支持文字消息，请直接输入你的数据查询需求。")
                return

            content = json.loads(msg.content)
            text = content.get("text", "").strip()

            if msg.chat_type == "group" and msg.mentions:
                for mention in msg.mentions:
                    text = text.replace(f"@_{mention.key}", "").strip()
                if not text:
                    self._reply(message_id, "你好！请输入你想查询的数据需求。")
                    return

            if not text:
                return

            logger.info("STI 飞书查询: user=%s, text=%s", user_id, text[:50])
            engine = _get_engine(user_id)
            result = engine.query(
                text,
                session_id=_feishu_memory_session_id(user_id),
                user_id=user_id,
            )

            reply = result.get("analysis") or result.get("error") or "抱歉，暂时无法处理你的请求。"
            self._reply(message_id, reply)

        except Exception:
            logger.exception("STI 飞书消息处理异常")
            try:
                self._reply(data.event.message.message_id, "系统处理异常，请稍后重试。")
            except Exception:
                pass

    def _reply(self, message_id: str, text: str) -> None:
        body = (
            ReplyMessageRequestBody.builder()
            .msg_type("text")
            .content(json.dumps({"text": text}, ensure_ascii=False))
            .build()
        )
        req = (
            ReplyMessageRequest.builder()
            .message_id(message_id)
            .request_body(body)
            .build()
        )
        resp = self.api_client.im.v1.message.reply(req)
        if not resp.success():
            logger.error("STI 飞书回复失败: code=%s, msg=%s", resp.code, resp.msg)

    def start_in_thread(self) -> None:
        if not self.app_id or not self.app_secret:
            logger.error("STI 飞书凭证缺失，跳过长连接启动")
            return
        t = threading.Thread(target=self._run_ws, name="sti-feishu-ws", daemon=True)
        t.start()
        logger.info("STI 飞书长连接线程已启动 (app_id=%s)", self.app_id)

    def _run_ws(self) -> None:
        import asyncio
        asyncio.set_event_loop(asyncio.new_event_loop())
        try:
            self.ws_client.start()
        except Exception:
            logger.exception("STI 飞书 WebSocket 异常退出")
