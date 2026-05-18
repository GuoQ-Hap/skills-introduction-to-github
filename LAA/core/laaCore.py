from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from admin.model_pool import model_pool
from LAA.models.laaState import LAAMatchResult
from LAA.models.laaState import LAAMatchRequest
from LAA.service.base import service_logger

logger = service_logger

_SYSTEM_PROMPT = """你是电商产品定位、人群场景洞察和卖点提炼专家。
请基于商品图片、评论/描述、颜色和尺寸，判断最匹配的人群、场景，并提炼可用于前端展示和 Listing 文案的核心卖点。

必须严格输出 JSON，不要输出任何额外说明。格式如下：
{
  "best_audience": "最匹配人群（短语）",
  "best_scene": "最匹配场景（短语）",
  "audience_candidates": [
    {"name": "候选人群", "reason": "结合图片/评论/颜色/尺寸说明原因", "score": 0}
  ],
  "scene_candidates": [
    {"name": "候选场景", "reason": "结合图片/评论/颜色/尺寸说明原因", "score": 0}
  ],
  "best_selling_point": "最强核心卖点（短语，8-18字）",
  "best_selling_point_reason": "为什么这个卖点最适合当前产品（1句话）",
  "best_selling_point_score": 0,
  "best_selling_point_candidates": [
    {"name": "候选卖点", "reason": "卖点成立原因", "score": 0}
  ],
  "insight": "简短综合洞察（不超过120字）"
}

规则：
1. score 范围 0-100，按匹配度从高到低排序。
2. audience_candidates、scene_candidates、best_selling_point_candidates 各给 3 条。
3. best_audience、best_scene、best_selling_point 必须来自各自候选列表的第一条。
4. 卖点必须是可直接给运营人员使用的表达，不要写成泛泛的“质量好”“适合使用”。
5. 卖点要结合产品视觉线索、评论/描述、颜色、尺寸、人群和场景。"""


def _extract_json(raw: str) -> Dict[str, Any]:
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def _candidate(name: str, reason: str, score: int) -> Dict[str, Any]:
    return {"name": name, "reason": reason, "score": score}


def _ensure_selling_points(data: Dict[str, Any]) -> Dict[str, Any]:
    selling_candidates = data.get("best_selling_point_candidates")
    if not isinstance(selling_candidates, list):
        selling_candidates = []

    selling_candidates = [item for item in selling_candidates if isinstance(item, dict) and item.get("name")]

    if not selling_candidates:
        audience = data.get("best_audience") or "目标用户"
        scene = data.get("best_scene") or "核心场景"
        insight = data.get("insight") or ""
        selling_candidates = [
            _candidate("精准匹配人群场景", f"围绕{audience}在{scene}中的使用需求提炼，便于直接转化为主卖点。", 88),
            _candidate("视觉风格强化吸引", f"结合图片视觉、颜色和尺寸信息，突出第一眼吸引力。{insight}", 82),
            _candidate("使用体验清晰表达", "从目标用户的实际使用场景出发，降低理解成本并提升购买决策效率。", 78),
        ]

    if not data.get("best_selling_point"):
        data["best_selling_point"] = selling_candidates[0].get("name", "")
    if not data.get("best_selling_point_reason"):
        data["best_selling_point_reason"] = selling_candidates[0].get("reason", "")
    if not data.get("best_selling_point_score"):
        data["best_selling_point_score"] = selling_candidates[0].get("score", 0)
    data["best_selling_point_candidates"] = selling_candidates[:3]
    return data


class LAAEngine:
    def match(self, req: LAAMatchRequest) -> tuple[LAAMatchResult, str]:
        user_blocks: List[Dict[str, Any]] = []
        if req.image_url:
            user_blocks.append({"type": "image_url", "image_url": {"url": req.image_url}})
        if req.image_base64:
            data_url = req.image_base64
            if not data_url.startswith("data:image"):
                data_url = f"data:image/jpeg;base64,{data_url}"
            user_blocks.append({"type": "image_url", "image_url": {"url": data_url}})

        user_blocks.append(
            {
                "type": "text",
                "text": (
                    "请分析以下商品信息，并输出最佳人群、最佳场景和核心卖点：\n"
                    f"- 评论/描述: {req.comment}\n"
                    f"- 颜色: {req.color}\n"
                    f"- 尺寸: {req.size}"
                ),
            }
        )

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_blocks},
        ]

        raw = model_pool.call_llm(
            messages=messages,
            temperature=0.2,
            max_tokens=1400,
            timeout=120,
            _log_module="laa_match",
            preferred_model=req.model,
        )

        data = _extract_json(raw)
        if not data:
            logger.warning("LAA JSON 解析失败，返回兜底结果")
            data = {
                "best_audience": "泛用消费人群",
                "best_scene": "日常使用场景",
                "audience_candidates": [_candidate("泛用消费人群", "模型输出未结构化，返回基础定位。", 70)],
                "scene_candidates": [_candidate("日常使用场景", "模型输出未结构化，返回基础场景。", 70)],
                "insight": "模型输出非结构化，已返回兜底结果，请重试或更换模型。",
            }

        data = _ensure_selling_points(data)
        result = LAAMatchResult.model_validate(data)
        return result, raw


laa_engine = LAAEngine()
