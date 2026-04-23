"""LLM 调用专用日志：所有大模型输入 / 输出统一写入 logs/llm.log。

用法::

    from Base.Config.llmLogConfig import log_llm_call

    log_llm_call(
        module="sti",
        model="gpt-5",
        messages=messages,
        response="...",
        latency_ms=123,
    )
"""
from __future__ import annotations

import json
import logging
import time
from logging.handlers import TimedRotatingFileHandler
from typing import Any, Dict, List, Optional, Union

from Base.RicUtils.pathUtils import find_project_root

_logger: Optional[logging.Logger] = None


def _get_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger

    _logger = logging.getLogger("llmlog")
    _logger.setLevel(logging.INFO)
    _logger.propagate = False

    log_dir = find_project_root() / "logs"
    log_dir.mkdir(exist_ok=True)

    handler = TimedRotatingFileHandler(
        filename=log_dir / "llm.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    handler.suffix = "%Y-%m-%d"
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    ))
    _logger.addHandler(handler)
    return _logger


def _truncate(text: str, limit: int = 2000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"...(truncated, total {len(text)} chars)"


def _serialize_messages(messages: Any) -> Any:
    """将 messages 统一转为可序列化的 list[dict]。"""
    if not messages:
        return messages
    result = []
    for m in messages:
        if isinstance(m, dict):
            result.append({
                "role": m.get("role", ""),
                "content": _truncate(str(m.get("content", ""))),
            })
        else:
            role = getattr(m, "role", "unknown")
            content = getattr(m, "content", str(m))
            result.append({"role": role, "content": _truncate(str(content))})
    return result


def log_llm_call(
    *,
    module: str,
    model: str,
    messages: Union[List[Dict], Any],
    response: Optional[str] = None,
    error: Optional[str] = None,
    latency_ms: Optional[int] = None,
    finish_reason: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """记录一次 LLM 调用的完整输入输出。

    Parameters
    ----------
    module : str
        调用来源，如 ``"sti"``、``"leang"``、``"base_chat"``。
    model : str
        模型名称，如 ``"gpt-5"``、``"qwen-max"``。
    messages : list
        发送给模型的完整 messages 列表。
    response : str, optional
        模型返回的文本内容。
    error : str, optional
        如果调用异常，记录错误信息。
    latency_ms : int, optional
        调用耗时（毫秒）。
    extra : dict, optional
        附加信息（temperature, max_tokens 等）。
    """
    record: Dict[str, Any] = {
        "module": module,
        "model": model,
        "messages": _serialize_messages(messages),
    }
    if response is not None:
        record["response"] = _truncate(response, 3000)
    if error is not None:
        record["error"] = str(error)[:1000]
    if latency_ms is not None:
        record["latency_ms"] = latency_ms
    if finish_reason is not None:
        record["finish_reason"] = finish_reason
    if extra:
        record["extra"] = extra

    try:
        _get_logger().info(json.dumps(record, ensure_ascii=False))
    except Exception:
        _get_logger().info(str(record))
