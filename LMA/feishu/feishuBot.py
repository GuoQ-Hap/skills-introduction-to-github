from __future__ import annotations

import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    ReplyMessageRequest,
    ReplyMessageRequestBody,
)

from LMA.core.qaCore import LeangQACore

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="feishu-qa")


class FeishuBot:
    """飞书长连接 RAG 问答机器人。

    通过 lark_oapi WebSocket 长连接接收消息，调用 LeangQACore 检索回答后回复。
    """

    def __init__(
        self,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
        collection_name: Optional[str] = None,
    ):
        self.app_id = app_id or os.getenv("FEISHU_APP_ID", "")
        self.app_secret = app_secret or os.getenv("FEISHU_APP_SECRET", "")
        self.collection_name = collection_name or os.getenv("FEISHU_COLLECTION_NAME") or None
        self._qa = LeangQACore()

        if not self.app_id or not self.app_secret:
            logger.warning("FEISHU_APP_ID / FEISHU_APP_SECRET 未配置，飞书机器人将无法启动")

        self.api_client = lark.Client.builder() \
            .app_id(self.app_id) \
            .app_secret(self.app_secret) \
            .log_level(lark.LogLevel.INFO) \
            .build()

        event_handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._on_message_receive)
            .build()
        )

        self.ws_client = lark.ws.Client(
            self.app_id,
            self.app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO,
        )

    def _on_message_receive(self, data: lark.im.v1.P2ImMessageReceiveV1) -> None:
        """收到飞书消息事件，提交到线程池异步处理。"""
        _executor.submit(self._handle_message, data)

    def _handle_message(self, data: lark.im.v1.P2ImMessageReceiveV1) -> None:
        try:
            msg = data.event.message
            message_id = msg.message_id

            if msg.message_type != "text":
                self._reply_text(message_id, "目前仅支持文本消息，请直接输入您的问题。")
                return

            content = json.loads(msg.content)
            question = content.get("text", "").strip()
            if not question:
                self._reply_text(message_id, "消息内容为空，请输入您的问题。")
                return

            logger.info("飞书问答请求: %s", question)
            chat_id = getattr(msg, "chat_id", None) or "default"
            session_id = f"leang-feishu-{chat_id}"
            sender = data.event.sender
            user_id = None
            if sender and sender.sender_id:
                user_id = sender.sender_id.open_id
            result = self._qa.ask(
                question,
                collection_name=self.collection_name,
                session_id=session_id,
                user_id=user_id,
                memory_turns=8,
            )

            if result.get("error"):
                answer = f"抱歉，处理出错：{result['error']}"
            else:
                answer = result.get("answer") or "未检索到相关内容，请换个问题试试。"

            self._reply_text(message_id, answer)

        except Exception:
            logger.exception("处理飞书消息异常")
            try:
                self._reply_text(
                    data.event.message.message_id,
                    "系统处理异常，请稍后重试。",
                )
            except Exception:
                logger.exception("异常回复也失败了")

    def _reply_text(self, message_id: str, text: str) -> None:
        """回复一条文本消息。"""
        body = (
            ReplyMessageRequestBody.builder()
            .msg_type("text")
            .content(json.dumps({"text": text}))
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
            logger.error(
                "飞书回复失败: code=%s, msg=%s, log_id=%s",
                resp.code, resp.msg, resp.get_log_id(),
            )

    def start_in_thread(self) -> None:
        """在守护线程中启动 WebSocket 长连接，不阻塞主线程。"""
        if not self.app_id or not self.app_secret:
            logger.error("飞书凭证缺失，跳过长连接启动")
            return

        t = threading.Thread(target=self._run_ws, name="feishu-ws", daemon=True)
        t.start()
        logger.info("飞书长连接线程已启动 (app_id=%s)", self.app_id)

    def _run_ws(self) -> None:
        import asyncio
        asyncio.set_event_loop(asyncio.new_event_loop())
        try:
            self.ws_client.start()
        except Exception:
            logger.exception("飞书 WebSocket 长连接异常退出")
