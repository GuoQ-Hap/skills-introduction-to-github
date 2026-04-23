"""后台任务管理服务。

使用内存字典存储任务状态，threading 执行长耗时 LLM 操作，
已完成任务自动清理（默认保留 30 分钟）。
"""
from __future__ import annotations

import threading
import time
import uuid
from enum import Enum
from typing import Any, Callable, Dict, Optional

from LSTA.service.base import service_logger

logger = service_logger

_TASK_TTL_SECONDS = 30 * 60  # 已完成任务保留 30 分钟
_CLEANUP_INTERVAL = 5 * 60   # 清理线程每 5 分钟扫描一次


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class _TaskEntry:
    __slots__ = (
        "task_id", "action", "status", "params_snapshot",
        "result", "partial", "error", "created_at", "finished_at",
    )

    def __init__(self, task_id: str, action: str, params_snapshot: dict):
        self.task_id = task_id
        self.action = action
        self.status = TaskStatus.PENDING
        self.params_snapshot: dict = params_snapshot
        self.result: Optional[Dict[str, Any]] = None
        # 运行中的阶段性产出（如多候选生成/评分进度），供前端实时渲染
        self.partial: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.created_at: float = time.time()
        self.finished_at: Optional[float] = None

    def elapsed_ms(self) -> int:
        end = self.finished_at or time.time()
        return int((end - self.created_at) * 1000)


class TaskStore:
    """线程安全的内存任务存储。"""

    def __init__(self):
        self._tasks: Dict[str, _TaskEntry] = {}
        self._lock = threading.Lock()
        self._start_cleanup_daemon()

    def create(self, action: str, params_snapshot: dict) -> str:
        task_id = uuid.uuid4().hex[:16]
        entry = _TaskEntry(task_id, action, params_snapshot)
        with self._lock:
            self._tasks[task_id] = entry
        return task_id

    def get(self, task_id: str) -> Optional[_TaskEntry]:
        with self._lock:
            return self._tasks.get(task_id)

    def mark_running(self, task_id: str):
        with self._lock:
            entry = self._tasks.get(task_id)
            if entry:
                entry.status = TaskStatus.RUNNING

    def mark_completed(self, task_id: str, result: dict):
        with self._lock:
            entry = self._tasks.get(task_id)
            if entry:
                entry.status = TaskStatus.COMPLETED
                entry.result = result
                entry.finished_at = time.time()

    def mark_failed(self, task_id: str, error: str):
        with self._lock:
            entry = self._tasks.get(task_id)
            if entry:
                entry.status = TaskStatus.FAILED
                entry.error = error
                entry.finished_at = time.time()

    def update_partial(self, task_id: str, partial: Dict[str, Any]):
        """线程安全地写入阶段性进度（供多候选等长流程推送实时结果）。"""
        with self._lock:
            entry = self._tasks.get(task_id)
            if entry:
                entry.partial = partial

    def delete(self, task_id: str) -> bool:
        with self._lock:
            return self._tasks.pop(task_id, None) is not None

    def to_dict(self, entry: _TaskEntry) -> dict:
        """将任务条目转为可序列化的字典。"""
        d: dict[str, Any] = {
            "task_id": entry.task_id,
            "status": entry.status.value,
            "action": entry.action,
            "elapsed_ms": entry.elapsed_ms(),
            "created_at": time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(entry.created_at),
            ),
            "asin": entry.params_snapshot.get("asin", ""),
            "marketplace": entry.params_snapshot.get("marketplace", ""),
        }
        if entry.status == TaskStatus.COMPLETED:
            d["result"] = entry.result
        if entry.status == TaskStatus.FAILED:
            d["error"] = entry.error
        # 运行中时携带 partial，完成后不再重复（result 里已有最终数据）
        if entry.status in (TaskStatus.PENDING, TaskStatus.RUNNING) and entry.partial:
            d["partial_result"] = entry.partial
        return d

    def run_in_thread(self, task_id: str, fn: Callable[[], dict]):
        """在后台线程中执行 fn，自动更新任务状态。"""

        def _worker():
            self.mark_running(task_id)
            try:
                result = fn()
                self.mark_completed(task_id, result)
                logger.info("后台任务完成: %s", task_id)
            except Exception as exc:
                self.mark_failed(task_id, str(exc))
                logger.error("后台任务失败: %s — %s", task_id, exc)

        t = threading.Thread(target=_worker, daemon=True, name=f"lsta-task-{task_id}")
        t.start()

    def _start_cleanup_daemon(self):
        def _cleaner():
            while True:
                time.sleep(_CLEANUP_INTERVAL)
                now = time.time()
                expired: list[str] = []
                with self._lock:
                    for tid, entry in self._tasks.items():
                        if entry.finished_at and (now - entry.finished_at) > _TASK_TTL_SECONDS:
                            expired.append(tid)
                    for tid in expired:
                        del self._tasks[tid]
                if expired:
                    logger.info("清理过期任务 %d 个", len(expired))

        t = threading.Thread(target=_cleaner, daemon=True, name="lsta-task-cleaner")
        t.start()

    def list_tasks(self) -> list[dict]:
        with self._lock:
            return [self.to_dict(e) for e in self._tasks.values()]


task_store = TaskStore()
