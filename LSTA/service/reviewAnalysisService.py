"""评论分析服务 —— 通过 LLM 从用户评论中提取痛点、卖点、核心特点。"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from admin.model_pool import model_pool
from LSTA.models.listingState import (
    CoreFeature,
    PainPoint,
    ReviewAnalysisResult,
    ReviewItem,
    SellingPoint,
)
from LSTA.service.base import service_logger

logger = service_logger

_SYSTEM_PROMPT = """你是一位资深的电商产品评论分析师。你的任务是从用户评论中提取有价值的商业洞察。

请严格按照以下 JSON 格式返回分析结果，不要包含任何其他文本：

```json
{
  "pain_points": [
    {
      "title": "痛点简述（10字以内）",
      "detail": "详细描述用户遇到的问题",
      "frequency": "high/medium/low",
      "related_reviews": [0, 2, 5]
    }
  ],
  "selling_points": [
    {
      "title": "卖点简述（10字以内）",
      "detail": "用户认可的产品优势",
      "frequency": "high/medium/low",
      "related_reviews": [1, 3]
    }
  ],
  "core_features": [
    {
      "title": "特点简述（10字以内）",
      "detail": "产品被提及最多的核心特征",
      "sentiment": "positive/neutral/negative"
    }
  ],
  "overall_sentiment": "positive/neutral/negative/mixed",
  "summary": "一段 100-200 字的综合分析摘要，概括评论反映的核心信息"
}
```

分析要求：
1. **痛点**：用户抱怨、不满、期望改进的方面。按出现频率从高到低排列。
2. **卖点**：用户明确表扬、推荐的方面。按出现频率从高到低排列。
3. **核心特点**：产品被反复提及的关键属性（不论好坏），如材质、尺寸、功能等。
4. **related_reviews** 为评论的索引号（从 0 开始），指向支撑该结论的原始评论。
5. **frequency** 基于在所有评论中出现的比例：high(>50%) / medium(20-50%) / low(<20%)。
6. 用中文回答，但保留产品相关的英文术语。"""


def _build_user_prompt(reviews: List[ReviewItem], product_title: str = "") -> str:
    parts = []
    if product_title:
        parts.append(f"产品：{product_title}\n")
    parts.append(f"共 {len(reviews)} 条评论：\n")
    for i, rv in enumerate(reviews):
        stars = f"{'★' * round(rv.stars)}{'☆' * (5 - round(rv.stars))}"
        line = f"[{i}] {stars} ({rv.stars}分)"
        if rv.title:
            line += f" {rv.title}"
        if rv.body:
            line += f"\n    {rv.body}"
        if rv.date:
            line += f"\n    ({rv.date})"
        parts.append(line)
    return "\n".join(parts)


def _parse_llm_response(raw: str) -> ReviewAnalysisResult:
    """从 LLM 返回的文本中提取 JSON 并映射到 ReviewAnalysisResult。"""
    json_match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
    if json_match:
        text = json_match.group(1)
    else:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        text = raw[start:end] if start >= 0 and end > start else raw

    data = json.loads(text)

    return ReviewAnalysisResult(
        pain_points=[PainPoint(**p) for p in data.get("pain_points", [])],
        selling_points=[SellingPoint(**s) for s in data.get("selling_points", [])],
        core_features=[CoreFeature(**f) for f in data.get("core_features", [])],
        overall_sentiment=data.get("overall_sentiment", ""),
        summary=data.get("summary", ""),
    )


class ReviewAnalysisService:
    """评论分析服务。"""

    def analyze(
        self,
        reviews: List[ReviewItem],
        product_title: str = "",
        model: str = "",
    ) -> ReviewAnalysisResult:
        if not reviews:
            raise ValueError("评论列表为空，无法分析")

        user_prompt = _build_user_prompt(reviews, product_title)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        logger.info("开始评论分析，共 %d 条评论，产品=%s", len(reviews), product_title[:50])

        kwargs: Dict[str, Any] = {
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 4096,
            "timeout": 120,
            "_log_module": "review_analysis",
        }
        if model:
            kwargs["preferred_model"] = model

        raw = model_pool.call_llm(**kwargs)
        logger.info("LLM 返回 %d 字符", len(raw))

        try:
            result = _parse_llm_response(raw)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("LLM 返回解析失败: %s\n原文: %s", e, raw[:500])
            result = ReviewAnalysisResult(
                summary=raw[:2000],
                overall_sentiment="unknown",
            )

        return result


review_analysis_service = ReviewAnalysisService()
