"""Listing 优化核心引擎。

流程：获取产品数据 → 构造提示词 → 调用 LLM → 解析优化结果
模型调用统一走 ModelPoolService.call_llm，主模型失败自动切换备用池。
"""
from __future__ import annotations

import concurrent.futures
import json
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from admin.model_pool import model_pool
from LSTA.constants import MARKETPLACE_LANGUAGES
from LSTA.models.listingState import (
    EvaluateAnalysis,
    EvaluateScores,
    FreeFormScore,
    OptimizedListing,
    OptimizedVariant,
    ProductData,
    ReviewAnalysisResult,
    TrafficWordDetail,
    WordAnalysis,
)
from LSTA.prompt.listingPrompt import (
    COSMO_OPTIMIZE_PROMPT,
    CTR_OPTIMIZE_PROMPT,
    CVR_OPTIMIZE_PROMPT,
    EVALUATE_LISTING_PROMPT,
    FREE_FORM_EVALUATE_PROMPT,
    PROMPT_DEFAULTS,
    REFINE_LISTING_PROMPT,
    TRAFFIC_OPTIMIZE_PROMPT,
    append_fab_to_prompt,
    build_custom_optimize_prompt,
    build_enhanced_optimize_prompt,
    build_optimize_prompt,
    build_system_prompt,
)
from LSTA.service.amazonService import amazon_service
from LSTA.service.base import service_logger

logger = service_logger


# ═══════════════════════════════════════════════
# LLM 全局节流
# ═══════════════════════════════════════════════
# 模型供应商限制：30 次/分钟、最多 4 并发、触发后冷却 20 秒。
# 采用「最小调用间隔 + 最大并发」双约束，避免命中 rate_limit_cooldown
# 而被迫降级到低质量备用模型（gpt-3.5-turbo-1106）。
LLM_MAX_CONCURRENCY = 3          # 低于供应商 4 并发上限
LLM_MIN_CALL_INTERVAL = 2.2      # 2.2s/次 → 理论上限 ≈27 次/分钟，安全余量


class _LlmRateLimiter:
    """简单节流器：保证多线程下 LLM 请求之间的最小间隔。"""

    def __init__(self, min_interval: float):
        self._lock = threading.Lock()
        self._last_call = 0.0
        self._min_interval = min_interval

    def wait(self) -> None:
        """调用方在发起 LLM 请求前调用，线程安全地等待节流时间片。"""
        with self._lock:
            now = time.monotonic()
            gap = now - self._last_call
            sleep_sec = self._min_interval - gap
            if sleep_sec > 0:
                time.sleep(sleep_sec)
            self._last_call = time.monotonic()


_LLM_THROTTLE = _LlmRateLimiter(min_interval=LLM_MIN_CALL_INTERVAL)

_LANGUAGE_NAMES = {
    "en": "English",
    "de": "Deutsch (German)",
    "ja": "日本語 (Japanese)",
    "fr": "Français (French)",
    "it": "Italiano (Italian)",
    "es": "Español (Spanish)",
}


class ListingOptimizer:
    """Amazon Listing 优化引擎。"""

    def fetch(self, asin: str, marketplace: str = "US") -> ProductData:
        """仅获取产品数据，不调用 LLM。"""
        return self._fetch_and_validate(asin, marketplace)

    def optimize(
        self,
        asin: str,
        marketplace: str = "US",
        target_keywords: Optional[List[str]] = None,
        target_audience: str = "",
        language: str = "",
        optimize_strategy: str = "standard",
        preferred_model: Optional[str] = None,
        prompt_overrides: Optional[Dict[str, str]] = None,
        product_data: Optional[ProductData] = None,
        optimize_sections: Optional[List[str]] = None,
        competitor_products: Optional[List[ProductData]] = None,
        custom_params: Optional[Dict[str, str]] = None,
        skip_traffic_analysis: bool = False,
        enable_fab: bool = False,
        review_analysis: Optional[ReviewAnalysisResult] = None,
        color: str = "",
    ) -> Dict[str, Any]:
        """调用 LLM 生成优化后的 Listing。

        两种模式：
        - enable_fab=True  → 增强路径（COSMO + FAB + 评论洞察 + 痛点检查）
        - enable_fab=False → 标准 SEO 路径

        参数：
            color: 产品颜色（来自 leang_product_info.colour）。非空时会以提示行的形式
                注入到 target_audience 开头，告诉 LLM 正确保留/突出该颜色属性。
        """
        product = product_data or self._fetch_and_validate(asin, marketplace)

        kw = target_keywords or []
        color_norm = (color or "").strip()
        if color_norm:
            color_hint = (
                f"【产品颜色】本品颜色为 {color_norm}，请在标题、五点、描述中准确保留并自然表达该颜色属性，"
                "避免改写成其它颜色或省略颜色信息。"
            )
            target_audience = (
                color_hint + ("\n\n" + target_audience if target_audience else "")
            )

        common_kwargs = dict(
            target_keywords=kw,
            target_audience=target_audience,
            language=language,
            preferred_model=preferred_model,
            prompt_overrides=prompt_overrides,
            competitor_products=competitor_products,
        )

        if enable_fab:
            result = self._optimize_enhanced_with_data(
                product, review_analysis=review_analysis,
                **common_kwargs,
            )
        else:
            result = self._optimize_with_data(
                product,
                target_keywords=kw,
                target_audience=target_audience,
                language=language,
                preferred_model=preferred_model,
                prompt_overrides=prompt_overrides,
                optimize_sections=optimize_sections,
                competitor_products=competitor_products,
                enable_fab=False,
            )

        if not skip_traffic_analysis:
            optimized: OptimizedListing = result.get("optimized")
            original: ProductData = result.get("original", product)
            if optimized:
                try:
                    word_analysis = self.analyze_traffic_words(
                        optimized=optimized,
                        product=original,
                        target_keywords=kw,
                        preferred_model=preferred_model,
                    )
                    optimized.word_analysis = word_analysis
                except Exception as e:
                    logger.warning("流量词分析失败（不影响主流程）: %s", e)

                # 校验用户勾选的关键词是否全部出现在优化结果中
                if kw and optimized:
                    all_text = " ".join([
                        optimized.title,
                        " ".join(optimized.bullet_points),
                        optimized.description,
                    ]).lower()
                    missing_kws = [k for k in kw if k.lower() not in all_text]
                    if missing_kws:
                        warn = f"\n\n⚠ 以下关键词未出现在优化结果中，建议手动补充或重新优化：{', '.join(missing_kws)}"
                        optimized.optimization_notes = (optimized.optimization_notes or "") + warn
                        logger.warning("优化结果缺少关键词: %s", missing_kws)

        return result

    def analyze(
        self, asin: str, marketplace: str = "US",
        search_terms: str = "",
        preferred_model: Optional[str] = None,
        product_data: Optional[ProductData] = None,
    ) -> Dict[str, Any]:
        """基于四维评判规则生成 Listing 诊断报告。"""
        product = product_data or self._fetch_and_validate(asin, marketplace)
        return self._analyze_with_data(
            product, search_terms=search_terms, preferred_model=preferred_model,
        )

    # ── 多候选优化（Best-of-N） ──────────────────

    # 候选差异化风格，按序循环使用
    _VARIANT_STYLES: List[Dict[str, str]] = [
        {"name": "情感共鸣", "desc": "侧重用户情绪价值、使用体验与场景沉浸感，文案富有感染力"},
        {"name": "功能驱动", "desc": "侧重技术规格、材质工艺、量化差异点，结构清晰、数据翔实"},
        {"name": "场景故事", "desc": "围绕典型使用场景展开故事化叙述，突出买回家后的生活画面"},
        {"name": "痛点解决", "desc": "开门见山点出核心痛点，再给出对应解决方案与证据支持"},
        {"name": "差异化对比", "desc": "强调相对于同类产品的差异优势，凸显独特卖点与量化对比"},
        {"name": "高端品质", "desc": "采用高端、简洁、质感化的文案风格，突出品牌调性与品质信任"},
        {"name": "性价比", "desc": "强调性价比、长期价值、多功能性，契合理性比价消费者"},
        {"name": "FAB 三段式", "desc": "每条要点严格按 Feature→Advantage→Benefit 层次推进"},
        {"name": "核心关键词前置", "desc": "核心高搜索量关键词在标题与要点首位显著曝光，紧密衔接 A9 权重"},
        {"name": "长尾覆盖", "desc": "在保持可读性的前提下尽可能覆盖同义词、变体与长尾搜索词"},
    ]

    def _build_variant_directive(self, index: int, total: int, base_audience: str) -> str:
        """为多候选模式构造差异化追加指令，附加到 target_audience 里。"""
        style = self._VARIANT_STYLES[index % len(self._VARIANT_STYLES)]
        base = base_audience.strip()
        directive = (
            f"\n\n[本次为候选 {index + 1}/{total}，为确保多候选间差异化，"
            f"本条请采用【{style['name']}】创作风格：{style['desc']}。"
            "在不违背产品事实与合规要求的前提下，尽量与其他候选拉开文案角度与用词差异。]"
        )
        return (base + directive) if base else directive.lstrip()

    def optimize_multi(
        self,
        asin: str,
        marketplace: str = "US",
        target_keywords: Optional[List[str]] = None,
        target_audience: str = "",
        language: str = "",
        optimize_strategy: str = "standard",
        preferred_model: Optional[str] = None,
        preferred_eval_model: Optional[str] = None,
        prompt_overrides: Optional[Dict[str, str]] = None,
        product_data: Optional[ProductData] = None,
        optimize_sections: Optional[List[str]] = None,
        competitor_products: Optional[List[ProductData]] = None,
        custom_params: Optional[Dict[str, str]] = None,
        skip_traffic_analysis: bool = False,
        enable_fab: bool = False,
        review_analysis: Optional[ReviewAnalysisResult] = None,
        variant_count: int = 3,
        search_terms_for_eval: str = "",
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
        color: str = "",
        tri_dim: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """并发生成 variant_count 份候选文案，并发调用 LLM 评分，择优标注。

        每个候选会同时产出两套评分：
        - 曝光评分（COSMO/关键词/Rufus/IDQ 四维规则打分，字段 scores / total_score）
        - 转化评分（LLM 仅从转化角度给出的 0-100 分，字段 free_form_score）

        最优候选由 composite_score = 曝光×w1 + 转化×w2 决定，权重取自三维诊断命中：
        - 仅『流量下降』命中 → (0.7, 0.3)
        - 仅『CTR/CVR 低』命中 → (0.3, 0.7)
        - 两类都命中或都不命中 → (0.5, 0.5)

        参数：
            preferred_eval_model: 评分阶段使用的模型，若为空则回退到 preferred_model
            tri_dim: 三维诊断数据（TriDimDiagnostic）。用于决定加权权重；为空时按 5:5 权重处理
            on_progress: 阶段性回调。每当一个候选完成生成/评分，会被调用，入参为
                {"phase": "generate|evaluate", "total": N, "generated": g,
                 "evaluated": e, "variants": [OptimizedVariant.model_dump(), ...]}

        返回：
            {
                "original": ProductData,
                "optimized": OptimizedListing,          # 最优候选（向前兼容）
                "variants": [OptimizedVariant, ...],     # 全部候选按 composite_score 倒序
                "best_variant_index": int,               # 最优候选在 variants 中的位置
                "tri_dim_hit": {...}                     # 命中摘要 + 实际采用的权重
            }
        """
        if variant_count < 1:
            variant_count = 1
        if variant_count > 10:
            variant_count = 10

        product = product_data or self._fetch_and_validate(asin, marketplace)
        kw = list(target_keywords or [])
        eval_model = preferred_eval_model or preferred_model

        # ── 阶段性进度状态（线程安全）──────────────
        # variants_map 以 variant_index 为键，值为 OptimizedVariant；边生成边评分边增量更新
        variants_map: Dict[int, OptimizedVariant] = {}
        progress_lock = threading.Lock()
        gen_done_count = 0
        eval_done_count = 0

        def _emit_progress(phase: str) -> None:
            """把当前已完成候选的快照推送给外部回调。"""
            if not on_progress:
                return
            try:
                with progress_lock:
                    snapshot = [
                        variants_map[k].model_dump()
                        for k in sorted(variants_map.keys())
                    ]
                    payload = {
                        "phase": phase,
                        "total": variant_count,
                        "generated": gen_done_count,
                        "evaluated": eval_done_count,
                        "variants": snapshot,
                    }
                on_progress(payload)
            except Exception as exc:  # 回调异常不应影响主流程
                logger.warning("on_progress 回调失败: %s", exc)

        def _generate_one(idx: int) -> tuple[int, Optional[OptimizedListing], Optional[str]]:
            """生成第 idx 个候选；多候选时追加差异化指令。"""
            nonlocal gen_done_count
            try:
                # 节流：避免打满供应商 30 次/分钟 & 4 并发限制
                _LLM_THROTTLE.wait()
                audience = self._build_variant_directive(idx, variant_count, target_audience) \
                    if variant_count > 1 else target_audience
                result = self.optimize(
                    asin=asin,
                    marketplace=marketplace,
                    target_keywords=kw,
                    target_audience=audience,
                    language=language,
                    optimize_strategy=optimize_strategy,
                    preferred_model=preferred_model,
                    prompt_overrides=prompt_overrides,
                    product_data=product,
                    optimize_sections=optimize_sections,
                    competitor_products=competitor_products,
                    custom_params=custom_params,
                    skip_traffic_analysis=True,
                    enable_fab=enable_fab,
                    review_analysis=review_analysis,
                    color=color,
                )
                listing = result.get("optimized")
                with progress_lock:
                    variants_map[idx] = OptimizedVariant(
                        variant_index=idx,
                        listing=listing or OptimizedListing(
                            optimization_notes=f"候选 {idx + 1} 生成失败",
                        ),
                        scores=None,
                        total_score=0,
                        overall_summary="",
                        priority_actions=[],
                        is_best=False,
                        generate_error=None,
                        evaluate_error=None,
                    )
                    gen_done_count += 1
                _emit_progress("generate")
                return idx, listing, None
            except Exception as e:
                logger.warning("候选 %d 生成失败: %s", idx + 1, e)
                with progress_lock:
                    variants_map[idx] = OptimizedVariant(
                        variant_index=idx,
                        listing=OptimizedListing(
                            optimization_notes=f"候选 {idx + 1} 生成失败：{e}",
                        ),
                        generate_error=str(e),
                    )
                    gen_done_count += 1
                _emit_progress("generate")
                return idx, None, str(e)

        # ── 1) 并行生成 ──────────────────────────
        logger.info(
            "开始多候选优化：ASIN=%s 站点=%s 候选数=%d", product.asin, product.marketplace, variant_count,
        )
        # 先推一次"初始"进度，便于前端立刻显示总数
        _emit_progress("init")

        gen_results: List[tuple[int, Optional[OptimizedListing], Optional[str]]] = []
        # 受供应商限流影响：并发不得超过 4（含备用模型切换时的重试），此处取 3
        max_workers = min(variant_count, LLM_MAX_CONCURRENCY)
        if variant_count == 1:
            gen_results.append(_generate_one(0))
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = [pool.submit(_generate_one, i) for i in range(variant_count)]
                for fu in concurrent.futures.as_completed(futures):
                    gen_results.append(fu.result())
        gen_results.sort(key=lambda x: x[0])

        # ── 2) 并行评分 ──────────────────────────
        # 每个候选都要跑两套评分：
        #   (a) COSMO 四维结构化评分（作为主排序依据）
        #   (b) 无因素评分（LLM 直接给 0-100 分，用于交叉参考）
        # 两者独立失败、独立写回，互不阻塞。
        def _evaluate_one(idx: int, listing: OptimizedListing) -> tuple[int, Optional[dict], Optional[str]]:
            nonlocal eval_done_count
            synthetic = self._build_synthetic_product(product, listing)
            search_terms_arg = search_terms_for_eval or listing.search_terms or ""

            def _run_cosmo() -> tuple[Optional[dict], Optional[str]]:
                try:
                    _LLM_THROTTLE.wait()
                    res = self._evaluate_with_data(
                        synthetic,
                        search_terms=search_terms_arg,
                        preferred_model=eval_model,
                    )
                    return res, None
                except Exception as ex:
                    logger.warning("候选 %d COSMO 四维评分失败: %s", idx + 1, ex)
                    return None, str(ex)

            def _run_free_form() -> tuple[Optional[FreeFormScore], Optional[str]]:
                try:
                    _LLM_THROTTLE.wait()
                    res = self._evaluate_free_form_with_data(
                        synthetic,
                        search_terms=search_terms_arg,
                        preferred_model=eval_model,
                    )
                    return (res or {}).get("free_form_score"), None
                except Exception as ex:
                    logger.warning("候选 %d 无因素评分失败: %s", idx + 1, ex)
                    return None, str(ex)

            # 两套评分并发执行，降低单候选评分耗时
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as inner:
                cosmo_future = inner.submit(_run_cosmo)
                ff_future = inner.submit(_run_free_form)
                cosmo_res, cosmo_err = cosmo_future.result()
                ff_score, ff_err = ff_future.result()

            scores = cosmo_res.get("scores") if cosmo_res else None
            with progress_lock:
                existing = variants_map.get(idx)
                if existing:
                    existing.scores = scores
                    existing.total_score = scores.total if scores else 0
                    existing.overall_summary = (cosmo_res or {}).get("overall_summary", "")
                    existing.priority_actions = (cosmo_res or {}).get("priority_actions", [])
                    existing.evaluate_error = cosmo_err
                    existing.free_form_score = ff_score
                    existing.free_form_error = ff_err
                eval_done_count += 1
            _emit_progress("evaluate")
            return idx, cosmo_res, cosmo_err

        eval_map: Dict[int, Optional[dict]] = {}
        eval_err_map: Dict[int, Optional[str]] = {}
        valid_for_eval = [(i, l) for i, l, _err in gen_results if l is not None]
        if valid_for_eval:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=min(len(valid_for_eval), LLM_MAX_CONCURRENCY),
            ) as pool:
                futures = [pool.submit(_evaluate_one, i, l) for i, l in valid_for_eval]
                for fu in concurrent.futures.as_completed(futures):
                    idx, res, err = fu.result()
                    eval_map[idx] = res
                    eval_err_map[idx] = err

        # ── 3) 组装 OptimizedVariant 列表 ─────────────
        # 无因素评分只写入了 variants_map 中的 existing 对象，这里需要回读后带入最终产物
        variants: List[OptimizedVariant] = []
        for idx, listing, gen_err in gen_results:
            eval_res = eval_map.get(idx)
            eval_err = eval_err_map.get(idx)
            scores: Optional[EvaluateScores] = eval_res.get("scores") if eval_res else None
            total = scores.total if scores else 0
            existing = variants_map.get(idx)
            ff_score = existing.free_form_score if existing else None
            ff_err = existing.free_form_error if existing else None
            variants.append(OptimizedVariant(
                variant_index=idx,
                listing=listing or OptimizedListing(
                    optimization_notes=f"候选 {idx + 1} 生成失败：{gen_err or '未知错误'}",
                ),
                scores=scores,
                total_score=total,
                overall_summary=(eval_res or {}).get("overall_summary", "") if eval_res else "",
                priority_actions=(eval_res or {}).get("priority_actions", []) if eval_res else [],
                is_best=False,
                generate_error=gen_err,
                evaluate_error=eval_err,
                free_form_score=ff_score,
                free_form_error=ff_err,
            ))

        # ── 根据三维诊断命中情况计算曝光/转化加权 ─────
        tri_hit_summary = self._compute_tri_dim_weights(tri_dim)
        w_expose = tri_hit_summary["weight_expose"]
        w_conv = tri_hit_summary["weight_conversion"]

        # 给每个候选算出复合分（用于最优排序）
        for v in variants:
            expose_pt = v.total_score or 0
            conv_pt = v.free_form_score.total if v.free_form_score else 0
            v.composite_score = round(expose_pt * w_expose + conv_pt * w_conv, 2)

        # 按复合分倒序；若全部失败则保持原序
        usable = [v for v in variants if v.listing and v.listing.title]
        if usable:
            variants.sort(
                key=lambda v: (
                    v.composite_score,
                    1 if v.scores else 0,
                    1 if v.free_form_score else 0,
                    -v.variant_index,
                ),
                reverse=True,
            )
            variants[0].is_best = True
            best_variant = variants[0]
        else:
            best_variant = variants[0] if variants else OptimizedVariant(listing=OptimizedListing(
                optimization_notes="全部候选生成均失败",
            ))
            if variants:
                variants[0].is_best = True

        # ── 4) 流量词分析仅针对最优候选 ─────────────
        if not skip_traffic_analysis and best_variant.listing and best_variant.listing.title:
            try:
                word_analysis = self.analyze_traffic_words(
                    optimized=best_variant.listing,
                    product=product,
                    target_keywords=kw,
                    preferred_model=preferred_model,
                )
                best_variant.listing.word_analysis = word_analysis
            except Exception as e:
                logger.warning("流量词分析失败（不影响主流程）: %s", e)

        # 补充最优标签到 optimization_notes 前缀，便于前端辨识
        total = len(variants)
        for rank, v in enumerate(variants):
            conv_pt = v.free_form_score.total if v.free_form_score else 0
            tag = (
                f"★ 综合最高（曝光{v.total_score}×{w_expose:.1f} + 转化{conv_pt}×{w_conv:.1f} = {v.composite_score}）"
                if v.is_best
                else f"曝光{v.total_score} | 转化{conv_pt} | 综合{v.composite_score}"
            )
            prefix = f"【候选 {v.variant_index + 1}/{total}】{tag}\n\n"
            note = v.listing.optimization_notes or ""
            if not note.startswith("【候选"):
                v.listing.optimization_notes = prefix + note

        # 最终再推一次完整进度（包含 is_best 标记与最终排名），便于前端拿到末态快照
        if on_progress:
            try:
                on_progress({
                    "phase": "done",
                    "total": variant_count,
                    "generated": gen_done_count,
                    "evaluated": eval_done_count,
                    "variants": [v.model_dump() for v in variants],
                    "tri_dim_hit": tri_hit_summary,
                })
            except Exception as exc:
                logger.warning("on_progress 末态回调失败: %s", exc)

        best_index = 0  # 排序后首项即最优
        return {
            "original": product,
            "optimized": best_variant.listing,
            "variants": variants,
            "best_variant_index": best_index,
            "tri_dim_hit": tri_hit_summary,
        }

    # ── 三维诊断阈值（与 triDimSqlService.TriDimThresholds 默认值保持一致） ──
    _TRI_DIM_CTR_THRESHOLD = 0.3   # 产品 CTR 百分比 < 该值视为候选命中
    _TRI_DIM_CVR_THRESHOLD = 10.0  # 产品 CVR 百分比 < 该值视为候选命中
    _TRI_DIM_SESS_DEC_THRESHOLD = 20.0  # 流量变化 < -该值（单位 %）视为下降命中

    @classmethod
    def _compute_tri_dim_weights(cls, tri_dim: Any) -> Dict[str, Any]:
        """根据三维诊断命中情况计算曝光/转化评分的权重。

        规则（用户确认）：
        - 仅命中『流量下降』 → 曝光 0.7 / 转化 0.3
        - 仅命中『CTR 或 CVR 低』 → 曝光 0.3 / 转化 0.7
        - 两类都命中 或 两类都不命中 → 曝光 0.5 / 转化 0.5
        """
        def _hit_flags(td: Any) -> tuple[bool, bool, bool]:
            if not td:
                return False, False, False
            try:
                sess_pct = getattr(td, "sessions_change_pct", None)
                p_ctr = getattr(td, "product_ctr_pct", None)
                c_ctr = getattr(td, "cat_avg_ctr_pct", None)
                p_cvr = getattr(td, "product_cvr_pct", None)
                c_cvr = getattr(td, "cat_avg_cvr_pct", None)
            except Exception:
                return False, False, False

            sess_dec = (
                sess_pct is not None
                and sess_pct < -cls._TRI_DIM_SESS_DEC_THRESHOLD
            )
            ctr_low = (
                p_ctr is not None and c_ctr is not None
                and p_ctr < c_ctr
                and p_ctr < cls._TRI_DIM_CTR_THRESHOLD
            )
            cvr_low = (
                p_cvr is not None and c_cvr is not None
                and p_cvr < c_cvr
                and p_cvr < cls._TRI_DIM_CVR_THRESHOLD
            )
            return sess_dec, ctr_low, cvr_low

        sess_dec, ctr_low, cvr_low = _hit_flags(tri_dim)
        conv_hit = ctr_low or cvr_low

        if sess_dec and not conv_hit:
            w_exp, w_conv = 0.7, 0.3
            rule = "仅命中『流量下降』→ 偏曝光权重 7:3"
        elif conv_hit and not sess_dec:
            w_exp, w_conv = 0.3, 0.7
            rule = "仅命中『CTR/CVR 低』→ 偏转化权重 3:7"
        else:
            w_exp, w_conv = 0.5, 0.5
            if sess_dec and conv_hit:
                rule = "流量与转化问题均命中 → 均衡权重 5:5"
            else:
                rule = "三维诊断无命中（或数据缺失）→ 均衡权重 5:5"

        return {
            "sessions_decline": sess_dec,
            "ctr_low": ctr_low,
            "cvr_low": cvr_low,
            "conversion_hit": conv_hit,
            "weight_expose": w_exp,
            "weight_conversion": w_conv,
            "rule": rule,
        }

    @staticmethod
    def _build_synthetic_product(original: ProductData, listing: OptimizedListing) -> ProductData:
        """基于优化后的文案构造用于四维评分的合成 ProductData。"""
        return ProductData(
            asin=original.asin,
            marketplace=original.marketplace,
            title=listing.title or original.title,
            brand=original.brand,
            price=original.price,
            currency=original.currency,
            rating=original.rating,
            review_count=original.review_count,
            bullet_points=list(listing.bullet_points) if listing.bullet_points else list(original.bullet_points or []),
            description=listing.description or original.description,
            category=original.category,
            bsr_rank=original.bsr_rank,
            images=list(original.images or []),
            reviews=list(original.reviews or []),
            variants=list(original.variants or []),
        )

    def evaluate(
        self,
        asin: str,
        marketplace: str = "US",
        search_terms: str = "",
        preferred_model: Optional[str] = None,
        product_data: Optional[ProductData] = None,
    ) -> Dict[str, Any]:
        """基于 COSMO/关键词/Rufus/IDQ 四维算法对 Listing 进行深度评判。"""
        product = product_data or self._fetch_and_validate(asin, marketplace)
        return self._evaluate_with_data(
            product, search_terms=search_terms, preferred_model=preferred_model,
        )

    def _evaluate_with_data(
        self,
        product: ProductData,
        search_terms: str = "",
        preferred_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """用已有产品数据调用 LLM 进行四维评判。"""
        bullet_text = (
            "\n".join(f"  - {b}" for b in product.bullet_points)
            if product.bullet_points else "  （无）"
        )

        prompt = EVALUATE_LISTING_PROMPT.format(
            system_prompt=build_system_prompt(),
            asin=product.asin,
            marketplace=product.marketplace,
            title=product.title or "（未获取到）",
            brand=product.brand or "（未知）",
            price=product.price or "N/A",
            currency=product.currency or "",
            rating=product.rating or "N/A",
            review_count=product.review_count or "0",
            category=product.category or "（未获取到）",
            bsr_rank=product.bsr_rank or "N/A",
            bullet_points_text=bullet_text,
            description=product.description or "（无）",
            search_terms=search_terms or "（未提供）",
        )

        messages = [{"role": "user", "content": prompt}]

        logger.info("正在调用 LLM 四维评判 Listing: ASIN=%s, 站点=%s", product.asin, product.marketplace)
        raw = model_pool.call_llm(
            messages,
            temperature=0.2,
            max_tokens=8192,
            timeout=300,
            _log_module="lAi_listing",
            preferred_model=preferred_model,
        )

        result = self._parse_evaluate_response(raw)
        return {
            "product": product,
            "scores": result.get("scores"),
            "analysis": result.get("analysis"),
            "overall_summary": result.get("overall_summary", ""),
            "priority_actions": result.get("priority_actions", []),
            "raw_output": raw if not result.get("scores") else "",
        }

    def _evaluate_free_form_with_data(
        self,
        product: ProductData,
        search_terms: str = "",
        preferred_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """无因素评分：把整段 Listing 直接交给 LLM，请它脱离任何规则/维度给出 0-100 分。

        与 _evaluate_with_data（COSMO 四维结构化评分）并列使用。
        """
        bullet_text = (
            "\n".join(f"  - {b}" for b in product.bullet_points)
            if product.bullet_points else "  （无）"
        )

        prompt = FREE_FORM_EVALUATE_PROMPT.format(
            system_prompt=build_system_prompt(),
            marketplace=product.marketplace or "",
            brand=product.brand or "（未知）",
            category=product.category or "（未获取到）",
            title=product.title or "（空）",
            bullet_points_text=bullet_text,
            description=product.description or "（空）",
            search_terms=search_terms or "（未提供）",
        )

        messages = [{"role": "user", "content": prompt}]
        logger.info("正在调用 LLM 无因素评分 Listing: ASIN=%s", product.asin)
        raw = model_pool.call_llm(
            messages,
            temperature=0.2,
            max_tokens=1024,
            timeout=180,
            _log_module="lAi_listing",
            preferred_model=preferred_model,
        )

        score = self._parse_free_form_response(raw)
        return {
            "product": product,
            "free_form_score": score,
            "raw_output": raw if score is None else "",
        }

    @staticmethod
    def _parse_free_form_response(raw: str) -> Optional[FreeFormScore]:
        """从 LLM 响应中解析无因素评分 JSON。"""
        cleaned = raw.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()

        data = ListingOptimizer._extract_json(cleaned)
        if not data or not isinstance(data, dict):
            logger.warning("LLM 无因素评分返回内容无法解析为 JSON")
            return None

        try:
            return FreeFormScore(
                total=int(data.get("total") or 0),
                summary=str(data.get("summary") or ""),
                strengths=list(data.get("strengths") or []),
                weaknesses=list(data.get("weaknesses") or []),
                suggestions=list(data.get("suggestions") or []),
            )
        except Exception as e:
            logger.warning("无因素评分 JSON 字段异常: %s", e)
            return None

    @staticmethod
    def _parse_evaluate_response(raw: str) -> Dict[str, Any]:
        """从 LLM 响应中解析四维评判 JSON 结果。"""
        cleaned = raw.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()

        data = ListingOptimizer._extract_json(cleaned)
        if data and isinstance(data, dict) and "scores" in data:
            scores_raw = data.get("scores", {})
            analysis_raw = data.get("analysis", {})

            try:
                scores = EvaluateScores(**scores_raw)
            except Exception:
                scores = EvaluateScores()

            try:
                analysis = EvaluateAnalysis(**analysis_raw)
            except Exception:
                analysis = EvaluateAnalysis()

            return {
                "scores": scores,
                "analysis": analysis,
                "overall_summary": data.get("overall_summary", ""),
                "priority_actions": data.get("priority_actions", []),
            }

        logger.warning("LLM 四维评判返回的内容无法解析为标准 JSON")
        return {
            "scores": None,
            "analysis": None,
            "overall_summary": "",
            "priority_actions": [],
        }

    def _optimize_cosmo_with_data(
        self,
        product: ProductData,
        target_keywords: List[str],
        target_audience: str,
        language: str,
        preferred_model: Optional[str] = None,
        prompt_overrides: Optional[Dict[str, str]] = None,
        competitor_products: Optional[List[ProductData]] = None,
        enable_fab: bool = False,
    ) -> Dict[str, Any]:
        """COSMO 四维策略优化：基于 COSMO/关键词/Rufus/IDQ 四维模型生成优化 Listing。"""
        lang_code = language or MARKETPLACE_LANGUAGES.get(product.marketplace, "en")
        lang_name = _LANGUAGE_NAMES.get(lang_code, lang_code)

        bullet_text = (
            "\n".join(f"  - {b}" for b in product.bullet_points)
            if product.bullet_points else "  （无）"
        )
        kw_text = (
            ", ".join(target_keywords) if target_keywords
            else "（未指定，请根据产品类型自动选择高搜索量关键词）"
        )
        audience_text = target_audience or "（未指定，请根据产品类型自动推断目标受众）"

        comp_section = ""
        if competitor_products:
            parts: list[str] = []
            for i, cp in enumerate(competitor_products, 1):
                bp = "\n".join(f"  - {b}" for b in cp.bullet_points) if cp.bullet_points else "  （无）"
                parts.append(
                    f"### 竞品 {i}（{cp.asin}）\n"
                    f"- **标题**: {cp.title or '（无）'}\n"
                    f"- **品牌**: {cp.brand or '（未知）'}\n"
                    f"- **价格**: {cp.price or 'N/A'} {cp.currency or ''}\n"
                    f"- **评分**: {cp.rating or 'N/A'}（{cp.review_count or '0'} 条评论）\n"
                    f"- **类目**: {cp.category or '（无）'}\n"
                    f"- **BSR 排名**: {cp.bsr_rank or 'N/A'}\n"
                    f"- **五点描述**:\n{bp}\n"
                    f"- **描述**: {cp.description or '（无）'}"
                )
            comp_section = (
                "\n## 竞品 Listing 参考\n"
                "请分析以下竞品的优劣势，在优化时取长补短、差异化竞争。\n\n"
                + "\n\n".join(parts) + "\n"
            )

        sys_prompt = build_system_prompt(prompt_overrides)
        prompt = COSMO_OPTIMIZE_PROMPT.format(
            system_prompt=sys_prompt,
            asin=product.asin,
            marketplace=product.marketplace,
            title=product.title or "（未获取到）",
            brand=product.brand or "（未知）",
            price=product.price or "N/A",
            currency=product.currency or "",
            rating=product.rating or "N/A",
            review_count=product.review_count or "0",
            category=product.category or "（未获取到）",
            bsr_rank=product.bsr_rank or "N/A",
            bullet_points_text=bullet_text,
            description=product.description or "（无）",
            competitor_section=comp_section,
            target_keywords=kw_text,
            target_audience=audience_text,
            output_language=f"请使用 **{lang_name}** 撰写优化后的 Listing 内容（优化说明用中文）",
        )
        if enable_fab:
            prompt = append_fab_to_prompt(prompt)

        messages = [{"role": "user", "content": prompt}]

        logger.info(
            "正在调用 LLM（COSMO 四维策略%s）优化 Listing: ASIN=%s, 站点=%s",
            " + FAB" if enable_fab else "", product.asin, product.marketplace,
        )
        raw = model_pool.call_llm(
            messages,
            temperature=0.7,
            max_tokens=6144,
            timeout=300,
            _log_module="lAi_listing",
            preferred_model=preferred_model,
        )

        optimized = self._parse_optimize_response(raw)
        return {
            "original": product,
            "optimized": optimized,
        }

    def _optimize_enhanced_with_data(
        self,
        product: ProductData,
        target_keywords: List[str],
        target_audience: str,
        language: str,
        review_analysis: ReviewAnalysisResult,
        preferred_model: Optional[str] = None,
        prompt_overrides: Optional[Dict[str, str]] = None,
        competitor_products: Optional[List[ProductData]] = None,
    ) -> Dict[str, Any]:
        """增强优化：COSMO + FAB + 评论洞察（仅生成 1 条主文案，不再产出备选）。"""
        lang_code = language or MARKETPLACE_LANGUAGES.get(product.marketplace, "en")
        lang_name = _LANGUAGE_NAMES.get(lang_code, lang_code)

        prompt = build_enhanced_optimize_prompt(
            system_prompt=build_system_prompt(prompt_overrides),
            product=product,
            target_keywords=target_keywords,
            target_audience=target_audience,
            output_language=f"请使用 **{lang_name}** 撰写优化后的 Listing 内容（优化说明用中文）",
            review_analysis=review_analysis,
            competitor_products=competitor_products,
            overrides=prompt_overrides,
        )

        messages = [{"role": "user", "content": prompt}]

        logger.info(
            "正在调用 LLM（增强 COSMO+FAB+评论洞察）优化 Listing: ASIN=%s, 站点=%s",
            product.asin, product.marketplace,
        )
        raw = model_pool.call_llm(
            messages,
            temperature=0.7,
            max_tokens=8192,
            timeout=360,
            _log_module="lAi_listing",
            preferred_model=preferred_model,
        )

        optimized = self._parse_optimize_response(raw)
        return {
            "original": product,
            "optimized": optimized,
        }

    # NOTE: regenerate_bullet（单条五点描述重新生成 3 条备选）已下线。
    # 原因：前端不再提供"3 条备选"入口，且该流程会额外占用 LLM 调用额度。

    def _build_competitor_section(self, competitor_products: Optional[List[ProductData]]) -> str:
        """构建竞品区段文本（供各 prompt 复用）。"""
        if not competitor_products:
            return ""
        parts: list[str] = []
        for i, cp in enumerate(competitor_products, 1):
            bp = "\n".join(f"  - {b}" for b in cp.bullet_points) if cp.bullet_points else "  （无）"
            parts.append(
                f"### 竞品 {i}（{cp.asin}）\n"
                f"- **标题**: {cp.title or '（无）'}\n"
                f"- **品牌**: {cp.brand or '（未知）'}\n"
                f"- **价格**: {cp.price or 'N/A'} {cp.currency or ''}\n"
                f"- **评分**: {cp.rating or 'N/A'}（{cp.review_count or '0'} 条评论）\n"
                f"- **类目**: {cp.category or '（无）'}\n"
                f"- **BSR 排名**: {cp.bsr_rank or 'N/A'}\n"
                f"- **五点描述**:\n{bp}\n"
                f"- **描述**: {cp.description or '（无）'}"
            )
        return (
            "\n## 竞品 Listing 参考\n"
            "请分析以下竞品的优劣势，在优化时取长补短、差异化竞争。\n\n"
            + "\n\n".join(parts) + "\n"
        )

    def _optimize_focused_with_data(
        self,
        product: ProductData,
        prompt_template: str,
        strategy_label: str,
        target_keywords: List[str],
        target_audience: str,
        language: str,
        preferred_model: Optional[str] = None,
        prompt_overrides: Optional[Dict[str, str]] = None,
        competitor_products: Optional[List[ProductData]] = None,
        enable_fab: bool = False,
    ) -> Dict[str, Any]:
        """通用侧重优化（CTR/CVR/流量）：使用指定 prompt_template 生成 Listing。"""
        lang_code = language or MARKETPLACE_LANGUAGES.get(product.marketplace, "en")
        lang_name = _LANGUAGE_NAMES.get(lang_code, lang_code)

        bullet_text = (
            "\n".join(f"  - {b}" for b in product.bullet_points)
            if product.bullet_points else "  （无）"
        )
        kw_text = (
            ", ".join(target_keywords) if target_keywords
            else "（未指定，请根据产品类型自动选择高搜索量关键词）"
        )
        audience_text = target_audience or "（未指定，请根据产品类型自动推断目标受众）"
        comp_section = self._build_competitor_section(competitor_products)

        sys_prompt = build_system_prompt(prompt_overrides)
        prompt = prompt_template.format(
            system_prompt=sys_prompt,
            asin=product.asin,
            marketplace=product.marketplace,
            title=product.title or "（未获取到）",
            brand=product.brand or "（未知）",
            price=product.price or "N/A",
            currency=product.currency or "",
            rating=product.rating or "N/A",
            review_count=product.review_count or "0",
            category=product.category or "（未获取到）",
            bsr_rank=product.bsr_rank or "N/A",
            bullet_points_text=bullet_text,
            description=product.description or "（无）",
            competitor_section=comp_section,
            target_keywords=kw_text,
            target_audience=audience_text,
            output_language=f"请使用 **{lang_name}** 撰写优化后的 Listing 内容（优化说明用中文）",
        )
        if enable_fab:
            prompt = append_fab_to_prompt(prompt)

        messages = [{"role": "user", "content": prompt}]
        logger.info(
            "正在调用 LLM（%s 侧重策略%s）优化 Listing: ASIN=%s, 站点=%s",
            strategy_label, " + FAB" if enable_fab else "", product.asin, product.marketplace,
        )
        raw = model_pool.call_llm(
            messages,
            temperature=0.7,
            max_tokens=6144,
            timeout=300,
            _log_module="lAi_listing",
            preferred_model=preferred_model,
        )
        optimized = self._parse_optimize_response(raw)
        return {"original": product, "optimized": optimized}

    def _optimize_custom_with_data(
        self,
        product: ProductData,
        custom_params: Dict[str, str],
        target_keywords: List[str],
        target_audience: str,
        language: str,
        preferred_model: Optional[str] = None,
        prompt_overrides: Optional[Dict[str, str]] = None,
        competitor_products: Optional[List[ProductData]] = None,
        enable_fab: bool = False,
    ) -> Dict[str, Any]:
        """自定义参数优化：按用户自定义指令生成 Listing。"""
        lang_code = language or MARKETPLACE_LANGUAGES.get(product.marketplace, "en")
        lang_name = _LANGUAGE_NAMES.get(lang_code, lang_code)

        bullet_text = (
            "\n".join(f"  - {b}" for b in product.bullet_points)
            if product.bullet_points else "  （无）"
        )
        kw_text = (
            ", ".join(target_keywords) if target_keywords
            else "（未指定，请根据产品类型自动选择高搜索量关键词）"
        )
        audience_text = target_audience or "（未指定，请根据产品类型自动推断目标受众）"
        comp_section = self._build_competitor_section(competitor_products)

        sys_prompt = build_system_prompt(prompt_overrides)
        prompt = build_custom_optimize_prompt(
            system_prompt=sys_prompt,
            asin=product.asin,
            marketplace=product.marketplace,
            title=product.title or "（未获取到）",
            brand=product.brand or "（未知）",
            price=product.price or "N/A",
            currency=product.currency or "",
            rating=product.rating or "N/A",
            review_count=product.review_count or "0",
            category=product.category or "（未获取到）",
            bsr_rank=product.bsr_rank or "N/A",
            bullet_points_text=bullet_text,
            description=product.description or "（无）",
            target_keywords=kw_text,
            target_audience=audience_text,
            output_language=f"请使用 **{lang_name}** 撰写优化后的 Listing 内容（优化说明用中文）",
            competitor_section=comp_section,
            custom_instructions=custom_params.get("custom_instructions", ""),
            tone=custom_params.get("tone", "professional"),
            focus_point=custom_params.get("focus_point", ""),
            extra_context=custom_params.get("extra_context", ""),
            title_strategy=custom_params.get("title_strategy", ""),
            bullet_style=custom_params.get("bullet_style", ""),
        )
        if enable_fab:
            prompt = append_fab_to_prompt(prompt)

        messages = [{"role": "user", "content": prompt}]
        logger.info(
            "正在调用 LLM（自定义策略%s）优化 Listing: ASIN=%s, 站点=%s",
            " + FAB" if enable_fab else "", product.asin, product.marketplace,
        )
        raw = model_pool.call_llm(
            messages,
            temperature=0.8,
            max_tokens=6144,
            timeout=300,
            _log_module="lAi_listing",
            preferred_model=preferred_model,
        )
        optimized = self._parse_optimize_response(raw)
        return {"original": product, "optimized": optimized}

    def _fetch_and_validate(self, asin: str, marketplace: str) -> ProductData:
        """获取产品数据并校验，title 非空视为成功，否则直接抛出异常，不调用 LLM。"""
        try:
            product = amazon_service.fetch(asin, marketplace)
        except Exception as e:
            logger.error("获取 ASIN %s 产品信息失败: %s", asin, e)
            raise ValueError(f"获取产品信息失败: {e}") from e

        if not product.title or not product.title.strip():
            logger.warning("ASIN %s 在 %s 站点未能获取到 title，判定为获取失败", asin, marketplace)
            raise ValueError(
                f"获取产品信息失败: ASIN {asin} 在 {marketplace} 站点未能解析到产品标题，"
                "可能是页面被反爬限制或 ASIN 无效，请稍后重试或检查 ASIN 是否正确"
            )

        logger.info("ASIN %s 产品信息获取成功: %s", asin, product.title[:80])
        return product

    def _optimize_with_data(
        self,
        product: ProductData,
        target_keywords: List[str],
        target_audience: str,
        language: str,
        preferred_model: Optional[str] = None,
        prompt_overrides: Optional[Dict[str, str]] = None,
        optimize_sections: Optional[List[str]] = None,
        competitor_products: Optional[List[ProductData]] = None,
        enable_fab: bool = False,
    ) -> Dict[str, Any]:
        """用已有产品数据调用 LLM 生成优化 Listing。"""
        lang_code = language or MARKETPLACE_LANGUAGES.get(product.marketplace, "en")
        lang_name = _LANGUAGE_NAMES.get(lang_code, lang_code)

        bullet_text = "\n".join(f"  - {b}" for b in product.bullet_points) if product.bullet_points else "  （无）"
        kw_text = ", ".join(target_keywords) if target_keywords else "（未指定，请根据产品类型自动选择高搜索量关键词）"
        audience_text = target_audience or "（未指定，请根据产品类型自动推断目标受众）"

        comp_texts: list[str] | None = None
        if competitor_products:
            comp_texts = []
            for i, cp in enumerate(competitor_products, 1):
                bp = "\n".join(f"  - {b}" for b in cp.bullet_points) if cp.bullet_points else "  （无）"
                comp_texts.append(
                    f"### 竞品 {i}（{cp.asin}）\n"
                    f"- **标题**: {cp.title or '（无）'}\n"
                    f"- **品牌**: {cp.brand or '（未知）'}\n"
                    f"- **价格**: {cp.price or 'N/A'} {cp.currency or ''}\n"
                    f"- **评分**: {cp.rating or 'N/A'}（{cp.review_count or '0'} 条评论）\n"
                    f"- **类目**: {cp.category or '（无）'}\n"
                    f"- **BSR 排名**: {cp.bsr_rank or 'N/A'}\n"
                    f"- **五点描述**:\n{bp}\n"
                    f"- **描述**: {cp.description or '（无）'}"
                )

        sys_prompt = build_system_prompt(prompt_overrides)
        prompt = build_optimize_prompt(
            system_prompt=sys_prompt,
            asin=product.asin,
            marketplace=product.marketplace,
            title=product.title or "（未获取到）",
            brand=product.brand or "（未知）",
            price=product.price or "N/A",
            currency=product.currency or "",
            rating=product.rating or "N/A",
            review_count=product.review_count or "0",
            category=product.category or "（未获取到）",
            bsr_rank=product.bsr_rank or "N/A",
            bullet_points_text=bullet_text,
            description=product.description or "（无）",
            target_keywords=kw_text,
            target_audience=audience_text,
            output_language=f"请使用 **{lang_name}** 撰写优化后的 Listing 内容（优化说明用中文）",
            overrides=prompt_overrides,
            sections=set(optimize_sections) if optimize_sections else None,
            competitor_texts=comp_texts,
        )

        if enable_fab:
            prompt = append_fab_to_prompt(prompt)

        messages = [{"role": "user", "content": prompt}]

        logger.info("正在调用 LLM 优化 Listing%s: ASIN=%s, 站点=%s",
                    " + FAB" if enable_fab else "", product.asin, product.marketplace)
        raw = model_pool.call_llm(
            messages,
            temperature=0.7,
            max_tokens=4096,
            timeout=300,
            _log_module="lAi_listing",
            preferred_model=preferred_model,
        )

        optimized = self._parse_optimize_response(raw)

        if optimize_sections:
            sec = set(optimize_sections)
            if "title" not in sec:
                optimized.title = product.title or ""
            if "bullet_points" not in sec:
                optimized.bullet_points = list(product.bullet_points or [])
            if "description" not in sec:
                optimized.description = product.description or ""
            if "search_terms" not in sec:
                optimized.search_terms = ""

        return {
            "original": product,
            "optimized": optimized,
        }

    def _analyze_with_data(
        self,
        product: ProductData,
        search_terms: str = "",
        preferred_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """使用四维评判规则（COSMO/关键词/Rufus/IDQ）生成诊断报告。"""
        eval_result = self._evaluate_with_data(
            product, search_terms=search_terms, preferred_model=preferred_model,
        )

        scores: EvaluateScores | None = eval_result.get("scores")
        analysis: EvaluateAnalysis | None = eval_result.get("analysis")
        overall_summary: str = eval_result.get("overall_summary", "")
        priority_actions: list = eval_result.get("priority_actions", [])

        text_parts: list[str] = []
        if overall_summary:
            text_parts.append(f"## 综合评判\n{overall_summary}")
        if scores:
            text_parts.append(
                f"## 四维得分（总分 {scores.total}/100）\n"
                f"- COSMO 关系覆盖: {scores.cosmo.subtotal}/25\n"
                f"- 关键词覆盖: {scores.keywords.subtotal}/25\n"
                f"- Rufus 语义覆盖: {scores.rufus.subtotal}/25\n"
                f"- IDQ 语义完整性: {scores.idq.subtotal}/25"
            )
        if analysis:
            for dim_name, dim_label in [
                ("cosmo", "COSMO 关系覆盖"),
                ("keywords", "关键词覆盖"),
                ("rufus", "Rufus 语义覆盖"),
                ("idq", "IDQ 语义完整性"),
            ]:
                dim = getattr(analysis, dim_name, None)
                if dim and dim.summary:
                    section = f"### {dim_label}\n{dim.summary}"
                    if dim.strengths:
                        section += "\n**优势:** " + "；".join(dim.strengths)
                    if dim.weaknesses:
                        section += "\n**不足:** " + "；".join(dim.weaknesses)
                    if dim.suggestions:
                        section += "\n**建议:** " + "；".join(dim.suggestions)
                    text_parts.append(section)
        if priority_actions:
            text_parts.append(
                "## 优先行动\n" + "\n".join(f"{i}. {a}" for i, a in enumerate(priority_actions, 1))
            )

        analysis_text = "\n\n".join(text_parts) if text_parts else eval_result.get("raw_output", "")

        return {
            "product": product,
            "analysis": analysis_text,
            "score": scores.total if scores else None,
            "scores": scores,
            "evaluate_analysis": analysis,
            "overall_summary": overall_summary,
            "priority_actions": priority_actions,
        }

    def refine(
        self,
        asin: str,
        marketplace: str,
        current_title: str,
        current_bullet_points: List[str],
        current_description: str,
        current_search_terms: str,
        user_feedback: str,
        preferred_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """根据用户反馈对现有 Listing 进行迭代修改。"""
        bullets_text = "\n".join(f"  - {b}" for b in current_bullet_points) if current_bullet_points else "  （无）"

        prompt = REFINE_LISTING_PROMPT.format(
            system_prompt=build_system_prompt(),
            asin=asin,
            marketplace=marketplace,
            current_title=current_title,
            current_bullets_text=bullets_text,
            current_description=current_description,
            current_search_terms=current_search_terms,
            user_feedback=user_feedback,
        )

        messages = [{"role": "user", "content": prompt}]

        logger.info("正在调用 LLM 迭代修改 Listing: ASIN=%s, 反馈=%s", asin, user_feedback[:80])
        raw = model_pool.call_llm(
            messages,
            temperature=0.7,
            max_tokens=4096,
            timeout=300,
            _log_module="lAi_listing",
            preferred_model=preferred_model,
        )

        optimized = self._parse_optimize_response(raw)
        return {"optimized": optimized}

    @staticmethod
    def _extract_json(text: str) -> Optional[dict]:
        """多层容错提取 JSON：直接解析 → 提取首个 {...} → 修复未闭合尾部。"""
        # 1) 直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 2) 提取第一个 { 到最后一个 } 之间的内容
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

        # 3) 从第一个 { 开始，尝试补全未闭合 JSON
        if start != -1:
            repaired = ListingOptimizer._repair_incomplete_json(text[start:])
            if repaired:
                try:
                    return json.loads(repaired)
                except json.JSONDecodeError:
                    pass

        # 4) 从第一个 { 开始，逐字符缩减尾部尝试解析（修复重复闭合符号）
        if start != -1:
            for i in range(end, start, -1):
                if text[i] == "}":
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        continue

        return None

    @staticmethod
    def _repair_incomplete_json(text: str) -> Optional[str]:
        """对明显被截断的 JSON 做轻量补全。"""
        if not text or "{" not in text:
            return None

        candidate = text.strip()

        # 去掉代码块尾部噪音
        candidate = re.sub(r"\s*```+\s*$", "", candidate).strip()

        # 若结尾停在字符串中间，先补一个引号
        quote_count = 0
        escape = False
        for ch in candidate:
            if ch == "\\" and not escape:
                escape = True
                continue
            if ch == '"' and not escape:
                quote_count += 1
            escape = False
        if quote_count % 2 == 1:
            candidate += '"'

        # 补齐括号/花括号
        stack: list[str] = []
        in_string = False
        escape = False
        for ch in candidate:
            if ch == "\\" and not escape:
                escape = True
                continue
            if ch == '"' and not escape:
                in_string = not in_string
            elif not in_string:
                if ch in "{[":
                    stack.append(ch)
                elif ch == "}" and stack and stack[-1] == "{":
                    stack.pop()
                elif ch == "]" and stack and stack[-1] == "[":
                    stack.pop()
            escape = False

        while stack:
            opener = stack.pop()
            candidate += "}" if opener == "{" else "]"

        # 若最后不是对象结束，尽量补成对象结束
        if candidate and not candidate.rstrip().endswith("}"):
            candidate = candidate.rstrip().rstrip(",")
            if not candidate.endswith("}"):
                candidate += "}"

        return candidate

    @staticmethod
    def _recover_partial_listing(raw: str) -> Optional[OptimizedListing]:
        """当完整 JSON 无法解析时，尽可能从半截 JSON 中抢救字段。"""
        text = raw.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()

        title_match = re.search(r'"title"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.DOTALL)
        search_terms_match = re.search(r'"search_terms"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.DOTALL)
        notes_match = re.search(r'"optimization_notes"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.DOTALL)
        bullets_match = re.search(r'"bullet_points"\s*:\s*\[(.*?)(?:\]\s*,|\]\s*\}|$)', text, re.DOTALL)
        desc_match = re.search(r'"description"\s*:\s*"((?:[^"\\]|\\.)*)', text, re.DOTALL)

        def _unescape(value: str) -> str:
            try:
                return json.loads(f'"{value}"')
            except Exception:
                return value.replace('\\"', '"').replace("\\n", "\n").replace("\\t", "\t")

        title = _unescape(title_match.group(1)) if title_match else ""
        search_terms = _unescape(search_terms_match.group(1)) if search_terms_match else ""
        optimization_notes = _unescape(notes_match.group(1)) if notes_match else ""
        description = _unescape(desc_match.group(1)) if desc_match else ""

        bullet_points: list[str] = []
        if bullets_match:
            bullet_points = [
                _unescape(m.group(1))
                for m in re.finditer(r'"((?:[^"\\]|\\.)*)"', bullets_match.group(1), re.DOTALL)
            ]

        if any([title, bullet_points, description, search_terms, optimization_notes]):
            return OptimizedListing(
                title=title,
                bullet_points=bullet_points,
                description=description,
                search_terms=search_terms,
                optimization_notes=optimization_notes or "LLM 返回 JSON 不完整，已自动抢救可解析字段。",
            )
        return None

    @staticmethod
    def _parse_optimize_response(raw: str) -> OptimizedListing:
        """从 LLM 响应中解析 JSON 格式的优化结果，兼容新旧两种格式。"""
        cleaned = raw.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()

        data = ListingOptimizer._extract_json(cleaned)
        if data and isinstance(data, dict):
            bullet_points: list[str] = data.get("bullet_points", []) or []

            # 向后兼容：若旧版 LLM 输出仍是 bullet_points_with_alternatives 结构，
            # 仅提取 primary 填入 bullet_points，不再保留备选。
            if not bullet_points:
                bwa_raw = data.get("bullet_points_with_alternatives", [])
                if isinstance(bwa_raw, list):
                    bullet_points = [
                        item.get("primary", "")
                        for item in bwa_raw
                        if isinstance(item, dict) and item.get("primary")
                    ]

            return OptimizedListing(
                title=data.get("title", ""),
                bullet_points=bullet_points,
                description=data.get("description", ""),
                search_terms=data.get("search_terms", ""),
                optimization_notes=data.get("optimization_notes", ""),
            )

        partial = ListingOptimizer._recover_partial_listing(raw)
        if partial:
            logger.warning("LLM 返回 JSON 不完整，已恢复部分字段")
            return partial

        logger.warning("LLM 返回的内容无法解析为 JSON，尝试从文本中提取")
        return OptimizedListing(
            title="",
            bullet_points=[],
            description="",
            search_terms="",
            optimization_notes=f"LLM 原始输出（JSON 解析失败）:\n\n{raw}",
        )

    @staticmethod
    def _extract_score(text: str) -> Optional[int]:
        """从分析文本中提取总分。"""
        patterns = [
            r"总分[：:]\s*(\d+)",
            r"总计[：:]\s*(\d+)",
            r"Total[:\s]*(\d+)",
            r"(\d+)\s*/\s*100",
        ]
        for pattern in patterns:
            m = re.search(pattern, text)
            if m:
                score = int(m.group(1))
                if 0 <= score <= 100:
                    return score
        return None

    # ── 流量词分析 ──────────────────────────────

    def analyze_traffic_words(
        self,
        optimized: OptimizedListing,
        product: ProductData,
        target_keywords: List[str],
        preferred_model: Optional[str] = None,
    ) -> WordAnalysis:
        """对优化结果中的词语进行流量词分析和产品相关性判定。"""
        from LSTA.service.trafficWordService import traffic_word_service

        check_result = traffic_word_service.batch_check_listing(
            title=optimized.title,
            bullet_points=optimized.bullet_points,
            description=optimized.description,
            search_terms=optimized.search_terms,
            target_keywords=target_keywords,
        )

        raw_traffic = check_result.get("traffic_words", [])
        if not raw_traffic:
            return WordAnalysis(
                traffic_words=[],
                keyword_words=target_keywords,
                description_words=[],
                total_checked=check_result.get("total_words_checked", 0),
            )

        # 用户在前端已完成流量词的人工筛选（target_keywords 即已选流量词）
        # 直接按是否在 target_keywords 中打标，无需再调 LLM 判定相关性
        kw_lower = {k.lower() for k in target_keywords}

        traffic_details = []
        for tw in raw_traffic:
            aba = tw.get("aba") or {}
            sqr = tw.get("sqr") or {}
            word_lower = tw["word"].lower()
            if word_lower in kw_lower:
                relevance = "clear"
                keep = True
            else:
                relevance = "unknown"
                keep = None
            traffic_details.append(TrafficWordDetail(
                word=tw["word"],
                aba_search_rank=aba.get("search_rank"),
                aba_record_count=aba.get("record_count", 0),
                sqr_total_impressions=sqr.get("search_query_count"),
                sqr_record_count=sqr.get("record_count", 0),
                relevance=relevance,
                keep=keep,
            ))

        description_words: List[str] = []

        listing_words = set(
            re.findall(r"[a-zA-Z][a-zA-Z'-]*[a-zA-Z]|[a-zA-Z]",
                       " ".join([optimized.title, " ".join(optimized.bullet_points),
                                 optimized.description]))
        )
        traffic_word_set = {td.word.lower() for td in traffic_details}
        for w in listing_words:
            low = w.lower()
            if low not in traffic_word_set and low not in kw_lower and len(low) >= 3:
                description_words.append(w)

        return WordAnalysis(
            traffic_words=traffic_details,
            keyword_words=target_keywords,
            description_words=description_words[:100],
            total_checked=check_result.get("total_words_checked", 0),
        )

    def assess_traffic_relevance(
        self,
        traffic_words: str,
        product: ProductData,
        target_keywords: Optional[List[str]] = None,
        preferred_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """调用 LLM 判定流量词对产品的描述准确性并给出替代词。"""
        if target_keywords is None:
            target_keywords = []
        if not traffic_words.strip():
            return {}

        kw_text = ", ".join(target_keywords) if target_keywords else "（无）"
        prompt = f"""你是 Amazon Listing 优化专家。请判断以下流量词对产品描述的准确程度。

## 产品信息
- 标题: {product.title or '（无）'}
- 类目: {product.category or '（无）'}
- 品牌: {product.brand or '（无）'}
- 目标关键词: {kw_text}

## 待判定的流量词
{traffic_words}

## 判定规则
- **clear**: 该词清晰准确地描述了产品，是产品的核心描述词、核心功能词或核心场景词
- **fuzzy**: 该词对产品的描述比较模糊，有一定关联但不够精准，可能匹配多种产品
- **broad**: 该词过于宽泛，是泛品类词或与产品关联很弱

## 输出要求
请严格按以下 JSON 格式输出（不要加 markdown 标记）：
{{
  "assessments": [
    {{
      "word": "流量词",
      "relevance": "clear/fuzzy/broad",
      "reason": "简要理由（20字内）",
      "alternatives": ["替代词1", "替代词2"]
    }}
  ]
}}

注意：alternatives 仅在 relevance 为 fuzzy 或 broad 时给出 2-3 个对产品描述更精准的替代搜索词。"""

        try:
            raw = model_pool.call_llm(
                [{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=4096,
                timeout=120,
                _log_module="lAi_listing",
                preferred_model=preferred_model,
            )

            data = self._extract_json(raw.strip().lstrip("`").lstrip("json").lstrip())
            if data and isinstance(data, dict):
                assessments = data.get("assessments", [])
                return {
                    a["word"].lower(): {
                        "relevance": a.get("relevance", "unknown"),
                        "reason": a.get("reason", ""),
                        "alternatives": a.get("alternatives", []),
                    }
                    for a in assessments
                    if isinstance(a, dict) and "word" in a
                }
        except Exception as e:
            logger.warning("流量词相关性判定失败: %s", e)

        return {}



listing_optimizer = ListingOptimizer()
