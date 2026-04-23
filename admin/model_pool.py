"""模型池管理 — 自动测试 / 主备切换 / 统一调用入口

启动时全量测试已配置的模型，通过的放入备用池，失败的放入失败列表。
外部通过 ``model_pool.call_llm(messages=...)`` 统一调用，主模型不可用
时自动遍历备用池选取下一个可用模型。

状态持久化到 ``model_pool.json``。
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI

from Base.Config.llmLogConfig import log_llm_call

from Base.Config.setting import settings
from Base.RicUtils.pathUtils import find_project_root

logger = logging.getLogger(__name__)

PROJECT_ROOT = find_project_root()
POOL_FILE = PROJECT_ROOT / "model_pool.json"
TEST_PROMPT = "请回答: 1+1等于几？只需给出数字答案。"
TEST_TIMEOUT = 30


class ModelPoolService:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._inited = False
                    cls._instance = inst
        return cls._instance

    def __init__(self):
        if self._inited:
            return
        self._inited = True
        self.primary: Optional[Dict] = None
        self.standby: List[Dict] = []
        self.failed: List[Dict] = []
        self.last_full_test: Optional[str] = None
        self._load()

    # ─────── 持久化 ───────

    def _load(self):
        if POOL_FILE.exists():
            try:
                data = json.loads(POOL_FILE.read_text("utf-8"))
                self.primary = data.get("primary")
                self.standby = data.get("standby", [])
                self.failed = data.get("failed", [])
                self.last_full_test = data.get("last_full_test")
                pname = self.primary["model"] if self.primary else "None"
                logger.info("模型池已从 model_pool.json 加载: 主模型=%s, 备用=%d, 失败=%d",
                            pname, len(self.standby), len(self.failed))
            except Exception as e:
                logger.warning("model_pool.json 加载失败: %s", e)

    def _save(self):
        try:
            POOL_FILE.write_text(json.dumps({
                "primary": self.primary,
                "standby": self.standby,
                "failed": self.failed,
                "last_full_test": self.last_full_test,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("model_pool.json 保存失败: %s", e)

    # ─────── 收集已配置模型 ───────

    def _collect_configured_models(self) -> List[Dict]:
        """收集所有 STI 系列模型（MODEL0~MODEL9）进入模型池。
        通义千问仅作为最终 fallback，不参与模型池选择。"""
        models: List[Dict] = []
        try:
            from LDA.constants import (
                STI_LLM_API_KEY, STI_LLM_BASE_URL, STI_LLM_MODELS,
            )
            if STI_LLM_API_KEY and STI_LLM_BASE_URL and STI_LLM_MODELS:
                for item in STI_LLM_MODELS:
                    idx = item["index"]
                    model_name = item["model"]
                    models.append({
                        "provider": f"sti_{idx}",
                        "provider_name": model_name,
                        "model": model_name,
                        "base_url": STI_LLM_BASE_URL,
                        "api_key": STI_LLM_API_KEY,
                    })
        except Exception:
            pass

        if settings.deepseek.api_key and settings.deepseek.base_url:
            models.append({
                "provider": "deepseek",
                "provider_name": "DeepSeek",
                "model": settings.deepseek.default_model or "deepseek-chat",
                "base_url": settings.deepseek.base_url,
                "api_key": settings.deepseek.api_key,
            })
        return models

    # ─────── 单模型测试 ───────

    @staticmethod
    def _collect_stream(client: OpenAI, model: str, messages: List[Dict],
                        max_tokens: int, timeout: int) -> tuple[str, str]:
        """流式调用并拼接完整文本，返回 (content, finish_reason)。"""
        stream = client.chat.completions.create(
            model=model, messages=messages,
            max_tokens=max_tokens, timeout=timeout, stream=True,
        )
        parts: List[str] = []
        finish_reason = ""
        for chunk in stream:
            choice = chunk.choices[0] if chunk.choices else None
            delta = choice.delta if choice else None
            if delta and delta.content:
                parts.append(delta.content)
            if choice and getattr(choice, "finish_reason", None):
                finish_reason = choice.finish_reason
        return "".join(parts), finish_reason

    def _test_one(self, m: Dict) -> Dict:
        uid = f"{m['provider']}:{m['model']}"
        test_msgs = [{"role": "user", "content": TEST_PROMPT}]
        start = time.time()
        try:
            client = OpenAI(
                api_key=m["api_key"],
                base_url=m["base_url"],
                max_retries=0,
                timeout=TEST_TIMEOUT,
            )
            raw = client.chat.completions.create(
                model=m["model"],
                messages=test_msgs,
                max_tokens=64,
            )
            finish_reason = raw.choices[0].finish_reason or ""
            resp = raw.choices[0].message.content or ""
            resp = re.sub(r"<think>.*?</think>", "", resp, flags=re.DOTALL).strip()

            if not resp:
                logger.info("[模型池] %s 非流式 content 为空，回退到流式", uid)
                resp, finish_reason = self._collect_stream(
                    client, m["model"], test_msgs, 64, TEST_TIMEOUT,
                )
                resp = re.sub(r"<think>.*?</think>", "", resp, flags=re.DOTALL).strip()

            elapsed = round(time.time() - start, 2)
            if not resp:
                raise ValueError("模型返回为空（流式/非流式均无内容）")

            log_llm_call(
                module="model_pool_test", model=uid,
                messages=test_msgs, response=resp,
                latency_ms=int(elapsed * 1000),
                finish_reason=finish_reason,
            )
            logger.info("[模型池] [PASS] %s 测试通过 (%.2fs): %s", uid, elapsed, resp[:60])
            return {
                "provider": m["provider"],
                "provider_name": m["provider_name"],
                "model": m["model"],
                "base_url": m["base_url"],
                "status": "ok",
                "latency": elapsed,
                "tested_at": datetime.now().isoformat(),
                "response_preview": resp[:80],
            }
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            log_llm_call(
                module="model_pool_test", model=uid,
                messages=test_msgs, error=str(e),
                latency_ms=int(elapsed * 1000),
            )
            logger.warning("[模型池] [FAIL] %s 测试失败 (%.2fs): %s", uid, elapsed, e)
            return {
                "provider": m["provider"],
                "provider_name": m["provider_name"],
                "model": m["model"],
                "base_url": m["base_url"],
                "status": "fail",
                "latency": elapsed,
                "tested_at": datetime.now().isoformat(),
                "error": str(e)[:300],
            }

    # ─────── 全量测试 ───────

    def run_full_test(self):
        logger.info("[模型池] >>> 开始全量模型测试 >>>")
        models = self._collect_configured_models()
        ok_list, fail_list = [], []

        for m in models:
            result = self._test_one(m)
            if result["status"] == "ok":
                ok_list.append(result)
            else:
                fail_list.append(result)

        if ok_list:
            old_primary = self.primary
            if old_primary:
                still_ok = any(
                    r["provider"] == old_primary["provider"] and r["model"] == old_primary["model"]
                    for r in ok_list
                )
                if still_ok:
                    self.primary = next(
                        r for r in ok_list
                        if r["provider"] == old_primary["provider"] and r["model"] == old_primary["model"]
                    )
                else:
                    logger.warning("[模型池] 主模型 %s 已失效，自动切换到 %s",
                                   old_primary["model"], ok_list[0]["model"])
                    self.primary = ok_list[0]
            else:
                self.primary = ok_list[0]

            self.standby = [r for r in ok_list if not (
                r["provider"] == self.primary["provider"] and r["model"] == self.primary["model"]
            )]
        else:
            self.primary = None
            self.standby = []

        self.failed = fail_list
        self.last_full_test = datetime.now().isoformat()
        self._save()

        logger.info("[模型池] >>> 全量测试完成: 通过=%d 失败=%d 主模型=%s >>>",
                     len(ok_list), len(fail_list),
                     self.primary["model"] if self.primary else "None")

    def run_full_test_async(self):
        t = threading.Thread(target=self.run_full_test, name="model-pool-test", daemon=True)
        t.start()

    # ─────── 单模型重测 ───────

    def retest_model(self, provider: str, model: str) -> Dict:
        models = self._collect_configured_models()
        target = next((m for m in models if m["provider"] == provider and m["model"] == model), None)
        if not target:
            return {"error": f"未找到 {provider}:{model}"}
        result = self._test_one(target)

        self.standby = [s for s in self.standby if not (s["provider"] == provider and s["model"] == model)]
        self.failed = [f for f in self.failed if not (f["provider"] == provider and f["model"] == model)]
        if self.primary and self.primary["provider"] == provider and self.primary["model"] == model:
            self.primary = None

        if result["status"] == "ok":
            if self.primary is None:
                self.primary = result
            else:
                self.standby.append(result)
        else:
            self.failed.append(result)
            if self.primary is None and self.standby:
                self.primary = self.standby.pop(0)

        self._save()
        return result

    # ─────── 状态查询 ───────

    def get_pool_status(self) -> Dict:
        return {
            "primary": self.primary,
            "standby": self.standby,
            "failed": self.failed,
            "last_full_test": self.last_full_test,
        }

    # ─────── 手动调整 ───────

    def set_primary(self, provider: str, model: str) -> bool:
        for i, s in enumerate(self.standby):
            if s["provider"] == provider and s["model"] == model:
                if self.primary:
                    self.standby.append(self.primary)
                self.primary = self.standby.pop(i)
                self._save()
                return True
        return False

    def add_to_standby(self, provider: str, model: str) -> bool:
        for i, f in enumerate(self.failed):
            if f["provider"] == provider and f["model"] == model:
                item = self.failed.pop(i)
                item["status"] = "ok"
                self.standby.append(item)
                self._save()
                return True
        return False

    def remove_from_standby(self, provider: str, model: str) -> bool:
        for i, s in enumerate(self.standby):
            if s["provider"] == provider and s["model"] == model:
                item = self.standby.pop(i)
                item["status"] = "fail"
                self.failed.append(item)
                self._save()
                return True
        return False

    # ─────── 对外 getter ───────

    def get_primary_model(self) -> Optional[Dict]:
        return self.primary

    def get_standby_models(self) -> List[Dict]:
        return list(self.standby)

    # ─────── 统一 LLM 调用入口 ───────

    @staticmethod
    def _pool_entry_passed_test(m: Optional[Dict]) -> bool:
        """仅展示已通过全量/单测的池内条目（拒绝 status=fail 或脏数据）。"""
        if not m or not m.get("provider") or not m.get("model"):
            return False
        return m.get("status", "ok") == "ok"

    def get_available_models(self) -> List[Dict]:
        """返回已通过验证且在池内的模型（主模型 + 备用），供前端选择。
        未写入 model_pool.json 或测试未通过的 .env 模型不会出现在此列表。"""
        models: List[Dict] = []
        if self._pool_entry_passed_test(self.primary):
            models.append({
                "id": f"{self.primary['provider']}:{self.primary['model']}",
                "provider": self.primary["provider"],
                "provider_name": self.primary.get("provider_name", self.primary["provider"]),
                "model": self.primary["model"],
                "is_primary": True,
            })
        for m in self.standby:
            if not self._pool_entry_passed_test(m):
                continue
            models.append({
                "id": f"{m['provider']}:{m['model']}",
                "provider": m["provider"],
                "provider_name": m.get("provider_name", m["provider"]),
                "model": m["model"],
                "is_primary": False,
            })
        return models

    def get_available_models_payload(self) -> Dict[str, Any]:
        """供 HTTP 接口使用：模型列表 + 最近一次全量测试时间（用于前端判断验证是否已跑完）。"""
        return {
            "models": self.get_available_models(),
            "last_full_test": self.last_full_test,
        }

    def call_llm(self, messages: List[Dict], temperature: float = 0.1,
                 max_tokens: int = 4096, timeout: int = 60,
                 _log_module: str = "model_pool",
                 preferred_model: Optional[str] = None) -> str:
        """统一 LLM 调用。主模型优先，失败后遍历备用池。
        preferred_model: 可选，格式 "provider:model"，指定后优先使用该模型。
        非流式 content 为空时自动回退到流式拼接。"""
        candidates = []
        if self.primary:
            candidates.append(self.primary)
        candidates.extend(self.standby)

        if preferred_model and ":" in preferred_model:
            prov, mod = preferred_model.split(":", 1)
            preferred = [c for c in candidates if c["provider"] == prov and c["model"] == mod]
            if preferred:
                others = [c for c in candidates if not (c["provider"] == prov and c["model"] == mod)]
                candidates = preferred + others
            else:
                logger.warning(
                    "[模型池] preferred_model 不在已验证池内，已忽略: %s", preferred_model,
                )

        if not candidates:
            raise RuntimeError("模型池为空，没有可用模型")

        last_err = None
        for idx, m in enumerate(candidates):
            t0 = time.time()
            model_name = f"{m['provider']}:{m['model']}"
            try:
                api_key = self._resolve_api_key(m["provider"])
                client = OpenAI(
                    api_key=api_key,
                    base_url=m["base_url"],
                    max_retries=0,
                    timeout=timeout,
                )
                resp = client.chat.completions.create(
                    model=m["model"],
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                finish_reason = resp.choices[0].finish_reason or ""
                content = resp.choices[0].message.content or ""
                content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

                if not content:
                    logger.info("[模型池] %s:%s 非流式 content 为空，回退到流式",
                                m["provider"], m["model"])
                    content, finish_reason = self._collect_stream(
                        client, m["model"], messages, max_tokens, timeout,
                    )
                    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

                elapsed = int((time.time() - t0) * 1000)
                log_llm_call(
                    module=_log_module,
                    model=model_name,
                    messages=messages,
                    response=content,
                    latency_ms=elapsed,
                    finish_reason=finish_reason,
                    extra={"temperature": temperature, "max_tokens": max_tokens},
                )

                if idx > 0:
                    logger.info("[模型池] 备用模型 %s:%s 调用成功，提升为主模型",
                                m["provider"], m["model"])
                    old_primary = self.primary
                    self.primary = m
                    self.standby = [s for s in self.standby if not (
                        s["provider"] == m["provider"] and s["model"] == m["model"]
                    )]
                    if old_primary:
                        self.standby.insert(0, old_primary)
                    self._save()

                return content
            except Exception as e:
                elapsed = int((time.time() - t0) * 1000)
                log_llm_call(
                    module=_log_module,
                    model=model_name,
                    messages=messages,
                    error=str(e),
                    latency_ms=elapsed,
                    extra={"temperature": temperature, "max_tokens": max_tokens},
                )
                last_err = e
                logger.warning("[模型池] %s:%s 调用失败: %s", m["provider"], m["model"], e)
                continue

        # 所有池内模型失败后，尝试通义千问作为最终 fallback
        if settings.dashscope.api_key and settings.dashscope.base_url:
            fb_model = settings.dashscope.default_model or "qwen-max"
            logger.info("[模型池] 所有模型失败，尝试通义千问 fallback: %s", fb_model)
            try:
                t0 = time.time()
                client = OpenAI(
                    api_key=settings.dashscope.api_key,
                    base_url=settings.dashscope.base_url,
                    max_retries=0,
                    timeout=timeout,
                )
                resp = client.chat.completions.create(
                    model=fb_model, messages=messages,
                    temperature=temperature, max_tokens=max_tokens,
                )
                finish_reason = resp.choices[0].finish_reason or ""
                content = resp.choices[0].message.content or ""
                content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
                if not content:
                    content, finish_reason = self._collect_stream(
                        client, fb_model, messages, max_tokens, timeout,
                    )
                    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
                elapsed = int((time.time() - t0) * 1000)
                log_llm_call(module=_log_module, model=f"dashscope:{fb_model}",
                             messages=messages, response=content, latency_ms=elapsed,
                             finish_reason=finish_reason)
                return content
            except Exception as e:
                logger.warning("[模型池] 通义千问 fallback 也失败: %s", e)
                last_err = e

        raise RuntimeError(f"所有模型均调用失败，最后错误: {last_err}")

    def _resolve_api_key(self, provider: str) -> str:
        if provider == "dashscope":
            return settings.dashscope.api_key
        if provider == "deepseek":
            return settings.deepseek.api_key
        if provider.startswith("sti"):
            from LDA.constants import STI_LLM_API_KEY
            return STI_LLM_API_KEY
        return settings.dashscope.api_key


model_pool = ModelPoolService()
