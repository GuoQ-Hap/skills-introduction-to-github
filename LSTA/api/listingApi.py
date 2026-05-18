"""lAi_listing FastAPI 接口"""
from __future__ import annotations

import json
import time
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from LSTA.core.listingCore import listing_optimizer
from LSTA.prompt.listingPrompt import PROMPT_DEFAULTS
from LSTA.models.listingState import (
    CustomOptimizeParams,
    FetchDiagnosticsResponse,
    FetchProductRequest,
    LAIHealthResponse,
    LingxingSubmitRequest,
    LingxingSubmitResponse,
    ListingAnalyzeRequest,
    ListingAnalyzeResponse,
    ListingDeepDiagnosticRequest,
    ListingDeepDiagnosticResponse,
    ListingDeepDiagnosticSection,
    ListingDeepComparisonSection,
    ListingCompetitorDiagnosticSection,
    ListingEmbedRequest,
    ListingEmbedResponse,
    ListingEvaluateRequest,
    ListingEvaluateResponse,
    ListingOptimizeRequest,
    ListingOptimizeResponse,
    ListingRefineRequest,
    ListingRefineResponse,
    ProductData,
    ReviewAnalysisResult,
    TaskListResponse,
    TaskStatusResponse,
    TaskSubmitRequest,
    TaskSubmitResponse,
    TrafficWordCheckRequest,
    TrafficWordCheckResponse,
    TrafficWordDecisionRequest,
    TrafficWordItem,
    TriDimDiagnostic,
    WordAnalysis,
    SearchTermRecommendRequest,
    SearchTermRecommendResponse,
    SqrSearchVolumeRequest,
    SqrSearchVolumeResponse,
    SqrSearchVolumesRequest,
    SqrSearchVolumesResponse,
    SpAdInsightQueryRequest,
    SpAdInsightResponse,
    SpAdInsightSyncRequest,
    ReviewAnalysisRequest,
    ReviewAnalysisResponse,
    CompetitorDiscoveryRequest,
    CompetitorDiscoveryResponse,
    MarketAnalysisRequest,
    MarketAnalysisResponse,
    AdStrategyAnalyzeRequest,
    AdStrategyActionCreateRequest,
    AdStrategyFeedbackRequest,
    ListingOptimizeRecordCreateRequest,
    ListingOptimizeRecordDeleteRequest,
    ListingOptimizeRecordDetailRequest,
    ListingOptimizeRecordQueryRequest,
    ListingOptimizeRecordStoreOptionsRequest,
    ListingOptimizeRecordUpdateRemarkRequest,
    ListingOptimizeRecordUpdateStoreRequest,
    TriDimDiagnosticSqlRequest,
    TriDimDiagnosticSqlResponse,
    TranslateRequest,
    TranslateResponse,
    MemoryFeedbackRequest,
    MemoryFeedbackResponse,
)
from LSTA.service.base import service_logger
from LSTA.service.lingxingService import lingxing_service
from LSTA.service.searchTermRecommendService import search_term_recommend_service
from LSTA.service.reviewAnalysisService import review_analysis_service
from LSTA.service.competitorDiscoveryService import discover_competitors
from LSTA.service.marketAnalysisService import market_analysis_service
from LSTA.service.adStrategyService import ad_strategy_service
from LSTA.service.listingOptimizeRecordService import listing_optimize_record_service
from LSTA.service.mwsReviewService import mws_review_service
from LSTA.service.triDimSqlService import build_diagnostic_count_sql, build_diagnostic_sql
from LSTA.service.sqrSearchVolumeService import sqr_search_volume_service
from LSTA.service.spAdInsightService import sp_ad_insight_service
from LSTA.service.taskService import task_store

logger = service_logger
router = APIRouter()


def _optional_user(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """从 Authorization 头解析当前用户名；未登录或 token 失效则返回 None（不抛错）。"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        from auth.service import get_user_by_token
        user = get_user_by_token(authorization[7:])
        return user.username if user else None
    except Exception:
        return None


def _persist_lsta(
    session_id: str,
    user_query: str,
    assistant_response: str,
    *,
    user_id: Optional[str] = None,
    intent: str = "optimize",
    latency_ms: int = 0,
    extra: dict | None = None,
) -> Optional[int]:
    """将 LSTA 操作结果写入 llm_memory，返回 memory_id（失败时 None）。"""
    try:
        from Base.Service.memoryDbService import memory_db
        return memory_db.save(
            "lsta", session_id, user_query,
            user_id=user_id,
            assistant_response=assistant_response,
            intent=intent,
            extra=extra,
            latency_ms=latency_ms,
        )
    except Exception as e:
        logger.warning("LSTA 持久化失败: %s", e)
        return None


@router.get("/health", response_model=LAIHealthResponse, summary="健康检查")
def health():
    from admin.model_pool import model_pool
    from version import APP_VERSION_FULL
    primary = model_pool.primary
    model_name = f"{primary['provider']}:{primary['model']}" if primary else "none"
    return LAIHealthResponse(
        status="ok",
        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        model=model_name,
        version=APP_VERSION_FULL,
    )


@router.get("/prompt-defaults", summary="获取提示词可配置默认值")
def get_prompt_defaults():
    return PROMPT_DEFAULTS


@router.post("/fetch", response_model=ProductData, summary="获取产品原始数据")
def fetch_product(req: FetchProductRequest):
    """仅获取 Amazon 产品数据，不调用 LLM。"""
    try:
        return listing_optimizer.fetch(asin=req.asin, marketplace=req.marketplace)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("产品数据获取异常")
        raise HTTPException(status_code=502, detail=f"获取失败: {e}")


@router.post("/fetch-with-diagnostics", response_model=FetchDiagnosticsResponse,
              summary="获取产品信息 + 三维诊断 + 流量词")
def fetch_with_diagnostics(req: FetchProductRequest):
    """获取 Amazon 产品数据，同时自动完成三维诊断和流量词发现。"""
    import concurrent.futures

    try:
        product = listing_optimizer.fetch(asin=req.asin, marketplace=req.marketplace)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("产品数据获取异常")
        raise HTTPException(status_code=502, detail=f"获取失败: {e}")

    tri_dim = None
    traffic_items: list[TrafficWordItem] = []
    sp_ad_items: list[dict] = []
    review_result = None
    mws_reviews: list = []
    mws_reviews: list = []

    def _fetch_tri_dim():
        try:
            return _query_tri_dim(req.asin)
        except Exception as exc:
            logger.warning("三维诊断查询失败: %s", exc)
            return None

    def _fetch_traffic_words():
        try:
            from LSTA.service.trafficWordService import traffic_word_service
            return traffic_word_service.batch_check_listing(
                title=product.title,
                bullet_points=product.bullet_points,
                description=product.description,
                search_terms="",
                target_keywords=[],
            )
        except Exception as exc:
            logger.warning("流量词查询失败: %s", exc)
            return None

    def _fetch_db_color():
        try:
            from LSTA.service.productDimService import query_product_color
            return query_product_color(req.asin)
        except Exception as exc:
            logger.warning("产品颜色查询失败: %s", exc)
            return ""

    def _fetch_sp_ad_insights():
        try:
            payload = sp_ad_insight_service.query(asin=req.asin, days=60, limit=60)
            return payload.get("items", [])
        except Exception as exc:
            logger.warning("SP 广告词洞察查询失败: %s", exc)
            return []

    def _fetch_mws_reviews():
        try:
            return mws_review_service.query_reviews_with_title(
                asin=req.asin,
                marketplace=req.marketplace,
                limit=100,
            )
        except Exception as exc:
            logger.warning("MWS 评论读取失败: %s", exc)
            return "", []

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        tri_future = pool.submit(_fetch_tri_dim)
        tw_future = pool.submit(_fetch_traffic_words)
        color_future = pool.submit(_fetch_db_color)
        sp_ad_future = pool.submit(_fetch_sp_ad_insights)
        mws_future = pool.submit(_fetch_mws_reviews)
        tri_dim = tri_future.result(timeout=180)
        tw_result = tw_future.result(timeout=180)
        db_color = color_future.result(timeout=30) or ""
        sp_ad_items = sp_ad_future.result(timeout=60) or []
        mws_title, mws_reviews = mws_future.result(timeout=120)

    if mws_reviews:
        product.reviews = mws_reviews
        if mws_title and not product.title:
            product.title = mws_title
        try:
            review_result = review_analysis_service.analyze(
                reviews=mws_reviews,
                product_title=product.title or mws_title,
            )
        except Exception as exc:
            logger.warning("评论分析失败（不影响主流程）: %s", exc)

    if tw_result:
        for tw in tw_result.get("traffic_words", []):
            aba = tw.get("aba") or {}
            sqr = tw.get("sqr") or {}
            has_aba = bool(aba)
            has_sqr = bool(sqr)
            source = "both" if has_aba and has_sqr else ("aba" if has_aba else "sqr")
            traffic_items.append(TrafficWordItem(
                word=tw["word"],
                aba_search_rank=aba.get("search_rank"),
                sqr_total_impressions=sqr.get("search_query_count"),
                source=source,
            ))

    # 流量词相关性 LLM 判定（发现词数 > 0 时执行）
    if traffic_items:
        try:
            words_str = ", ".join(item.word for item in traffic_items[:60])
            relevance_map = listing_optimizer.assess_traffic_relevance(
                traffic_words=words_str,
                product=product,
            )
            for item in traffic_items:
                rel_info = relevance_map.get(item.word.lower(), {})
                item.relevance = rel_info.get("relevance", "unknown")
                item.reason = rel_info.get("reason", "")
        except Exception as exc:
            logger.warning("流量词相关性判定失败（不影响主流程）: %s", exc)

    existing_words = {item.word.lower() for item in traffic_items}
    for item in sp_ad_items:
        word = str(item.get("word_text") or "").strip().lower()
        if not word or word in existing_words:
            continue
        existing_words.add(word)
        traffic_items.append(TrafficWordItem(
            word=word,
            aba_search_rank=None,
            sqr_total_impressions=int(item.get("impressions") or 0),
            source="sp_ads",
            relevance="clear" if item.get("insight_type") == "high_conversion" else "unknown",
            reason=item.get("reason") or item.get("insight_type") or "AK SP ad insight",
        ))

    return FetchDiagnosticsResponse(
        product=product,
        tri_dim=tri_dim,
        traffic_words=traffic_items,
        traffic_word_count=len(traffic_items),
        sp_ad_insights=_sp_ad_insight_items(sp_ad_items),
        sp_ad_insight_count=len(sp_ad_items),
        review_analysis=review_result,
        db_color=db_color,
    )


def _query_tri_dim(asin: str) -> TriDimDiagnostic | None:
    """通过 Doris(LDA) 查询单个 ASIN 的三维诊断数据（SQL 与 triDimSqlService 统一）。"""
    from LDA.service.dbService import db_service

    sql = build_diagnostic_sql(
        30,
        asin=asin,
        page=1,
        page_size=1,
        dims=None,
        thresholds=None,
        row_filter=False,
    )
    _, rows = db_service.execute_sql(sql)
    if not rows:
        return None
    r = rows[0]
    return TriDimDiagnostic(
        product_ctr_pct=_safe_float(r.get("product_ctr_pct")),
        cat_avg_ctr_pct=_safe_float(r.get("cat_avg_ctr_pct")),
        product_cvr_pct=_safe_float(r.get("product_cvr_pct")),
        cat_avg_cvr_pct=_safe_float(r.get("cat_avg_cvr_pct")),
        sessions_change_pct=_safe_float(r.get("sessions_change_pct")),
        avg_stock_qty=int(r["avg_stock_qty"]) if r.get("avg_stock_qty") is not None else None,
        hit_count=int(r.get("hit_count", 0)),
        optimization_actions=r.get("optimization_actions") or "",
        msku=r.get("msku") or "",
        store_name=r.get("store_name") or "",
        country_code=r.get("country_code") or "",
        category_2=r.get("category_2") or "",
        total_volume=int(r["total_volume"]) if r.get("total_volume") is not None else None,
        total_amount=_safe_float(r.get("total_amount")),
    )


def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


@router.post(
    "/tri-dim-diagnostic-sql",
    response_model=TriDimDiagnosticSqlResponse,
    summary="生成三维诊断 SQL（单一来源，供前端 LDA execSql 与后端共用）",
)
def tri_dim_diagnostic_sql(req: TriDimDiagnosticSqlRequest):
    """返回与 triDimSqlService 一致的数据 SQL；可选附带 count_sql。"""
    th = req.thresholds
    data_sql = build_diagnostic_sql(
        req.date_range,
        asin=req.asin,
        page=req.page,
        page_size=req.page_size,
        dims=req.dims,
        thresholds=th,
        row_filter=req.row_filter,
        sales_apartment=req.sales_apartment,
    )
    count_sql = None
    if req.include_count_sql:
        count_sql = build_diagnostic_count_sql(
            req.date_range,
            asin=req.asin,
            dims=req.dims,
            thresholds=th,
            row_filter=req.row_filter,
            sales_apartment=req.sales_apartment,
        )
    return TriDimDiagnosticSqlResponse(data_sql=data_sql, count_sql=count_sql)


def _sp_ad_insight_items(rows: list[dict]) -> list[dict]:
    items: list[dict] = []
    for row in rows:
        item = dict(row)
        for key in ("date_start", "date_end", "updated_at"):
            if item.get(key) is not None:
                item[key] = str(item[key])
        for key in ("cost", "sales", "ctr", "cpc", "cvr", "acos", "roas"):
            if item.get(key) is not None:
                try:
                    item[key] = float(item[key])
                except Exception:
                    item[key] = 0
        items.append(item)
    return items


@router.post("/sp-ad-insights/sync", summary="同步 AK 店铺 SP 广告词洞察缓存")
def sync_sp_ad_insights(req: SpAdInsightSyncRequest):
    try:
        return sp_ad_insight_service.sync(
            days=req.days,
            asin=req.asin,
            limit_per_type=req.limit_per_type,
        )
    except Exception as e:
        logger.exception("SP 广告词洞察同步失败")
        raise HTTPException(status_code=500, detail=f"SP 广告词洞察同步失败: {e}")


@router.post("/sp-ad-insights", response_model=SpAdInsightResponse, summary="查询 AK 店铺 SP 广告词洞察")
def query_sp_ad_insights(req: SpAdInsightQueryRequest):
    try:
        payload = sp_ad_insight_service.query(
            asin=req.asin,
            store_name=req.store_name or None,
            days=req.days,
            limit=req.limit,
        )
        payload["items"] = _sp_ad_insight_items(payload.get("items", []))
        return SpAdInsightResponse(**payload)
    except Exception as e:
        logger.exception("SP 广告词洞察查询失败")
        raise HTTPException(status_code=500, detail=f"SP 广告词洞察查询失败: {e}")


@router.post("/optimize", response_model=ListingOptimizeResponse, summary="Listing 优化")
def optimize_listing(req: ListingOptimizeRequest, user_id: Optional[str] = Depends(_optional_user)):
    """输入 ASIN，自动获取产品数据并生成优化后的 Listing。

    当 variant_count>1 时，并发生成多份候选并用 LLM 四维评分择优。
    """
    t0 = time.time()
    try:
        overrides: dict[str, str] | None = None
        if req.prompt_overrides:
            overrides = {k: v for k, v in req.prompt_overrides.items() if v and v.strip()}
            if not overrides:
                overrides = None
        custom_params_dict: dict | None = None
        if req.custom_params:
            custom_params_dict = req.custom_params.model_dump(exclude_none=True)

        color_for_optimize = (req.color or "").strip()
        if not color_for_optimize:
            try:
                from LSTA.service.productDimService import query_product_color
                color_for_optimize = query_product_color(req.asin)
            except Exception as exc:
                logger.warning("优化接口: 查询产品颜色失败（忽略）: %s", exc)
                color_for_optimize = ""

        # 三维诊断兜底：前端未带 tri_dim 时自动查询，用于候选加权选最优
        tri_dim_for_optimize = req.tri_dim
        if tri_dim_for_optimize is None and req.variant_count and req.variant_count > 1:
            try:
                tri_dim_for_optimize = _query_tri_dim(req.asin)
            except Exception as exc:
                logger.warning("优化接口: 兜底查询三维诊断失败（忽略）: %s", exc)
                tri_dim_for_optimize = None

        sp_ad_rows: list[dict] = []
        try:
            if req.sp_ad_insights:
                sp_ad_rows = [x.model_dump() for x in req.sp_ad_insights]
            else:
                sp_payload = sp_ad_insight_service.query(asin=req.asin, days=60, limit=30)
                sp_ad_rows = _sp_ad_insight_items(sp_payload.get("items", []))
        except Exception as exc:
            logger.warning("优化接口: SP 广告词洞察读取失败（忽略）: %s", exc)
            sp_ad_rows = []

        sp_words, sp_prompt = sp_ad_insight_service.top_words_for_prompt(sp_ad_rows, limit=20)
        merged_kw = list(req.target_keywords or [])
        seen_kw = {k.strip().lower() for k in merged_kw if k and k.strip()}
        for word in sp_words:
            low = word.strip().lower()
            if low and low not in seen_kw:
                merged_kw.append(word.strip())
                seen_kw.add(low)

        target_audience_for_optimize = req.target_audience
        if sp_prompt:
            ad_block = (
                "\n\n[AK SP广告真实投放洞察]\n"
                "以下词来自AK店铺领星SP广告数据。high_conversion词优先自然覆盖到标题/五点/Search Terms；"
                "high_click_no_order词不要机械堆砌，应检查并补强Listing承接；"
                "high_impression_low_ctr词仅在强相关时使用。\n"
                f"{sp_prompt}"
            )
            target_audience_for_optimize = (target_audience_for_optimize or "") + ad_block

        common_kwargs = dict(
            asin=req.asin,
            marketplace=req.marketplace,
            target_keywords=merged_kw,
            target_audience=target_audience_for_optimize,
            language=req.language,
            optimize_strategy=req.optimize_strategy.value,
            preferred_model=req.model,
            prompt_overrides=overrides,
            product_data=req.product_data,
            optimize_sections=req.optimize_sections,
            competitor_products=req.competitor_products,
            custom_params=custom_params_dict,
            enable_fab=req.enable_fab,
            skip_traffic_analysis=True,
            review_analysis=req.review_analysis,
            color=color_for_optimize,
        )

        if req.variant_count and req.variant_count > 1:
            result = listing_optimizer.optimize_multi(
                variant_count=req.variant_count,
                preferred_eval_model=req.eval_model,
                tri_dim=tri_dim_for_optimize,
                **common_kwargs,
            )
        else:
            result = listing_optimizer.optimize(**common_kwargs)

        resp = ListingOptimizeResponse(
            asin=req.asin,
            marketplace=req.marketplace,
            original=result["original"],
            optimized=result["optimized"],
            variants=result.get("variants", []),
            best_variant_index=result.get("best_variant_index"),
            tri_dim_hit=result.get("tri_dim_hit"),
        )
        latency = int((time.time() - t0) * 1000)
        base_extra = {"asin": req.asin, "marketplace": req.marketplace}
        if resp.variants and len(resp.variants) > 1:
            # 多候选：每个 variant 单独一条记忆，方便逐条溯源
            var_mem_ids: List[Optional[int]] = []
            for idx, v in enumerate(resp.variants):
                vid = _persist_lsta(
                    req.session_id,
                    f"优化 Listing (候选{idx+1}): {req.asin} ({req.marketplace})",
                    json.dumps(v.listing.model_dump(), ensure_ascii=False)[:2000],
                    user_id=user_id,
                    intent="optimize",
                    latency_ms=latency,
                    extra={**base_extra, "variant_index": idx, "variant_score": v.composite_score},
                )
                var_mem_ids.append(vid)
            resp.variant_memory_ids = var_mem_ids
            # memory_id 指向最优候选
            best_idx = result.get("best_variant_index") or 0
            resp.memory_id = var_mem_ids[best_idx] if var_mem_ids else None
        else:
            mem_id = _persist_lsta(
                req.session_id,
                f"优化 Listing: {req.asin} ({req.marketplace})",
                json.dumps(resp.optimized.model_dump(), ensure_ascii=False)[:2000],
                user_id=user_id,
                intent="optimize",
                latency_ms=latency,
                extra=base_extra,
            )
            resp.memory_id = mem_id
        return resp
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        logger.error("Listing 优化失败: %s", e)
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.exception("Listing 优化异常")
        raise HTTPException(status_code=500, detail=f"优化过程出错: {e}")


@router.post("/analyze", response_model=ListingAnalyzeResponse,
              summary="Listing 诊断分析（四维评判：COSMO/关键词/Rufus/IDQ）")
def analyze_listing(req: ListingAnalyzeRequest, user_id: Optional[str] = Depends(_optional_user)):
    """基于 COSMO/关键词/Rufus/IDQ 四维算法规则对 Listing 进行诊断分析。"""
    t0 = time.time()
    try:
        result = listing_optimizer.analyze(
            asin=req.asin,
            marketplace=req.marketplace,
            search_terms=req.search_terms,
            preferred_model=req.model,
            product_data=req.product_data,
        )
        resp = ListingAnalyzeResponse(
            asin=req.asin,
            marketplace=req.marketplace,
            product=result["product"],
            analysis=result["analysis"],
            score=result.get("score"),
            scores=result.get("scores"),
            evaluate_analysis=result.get("evaluate_analysis"),
            overall_summary=result.get("overall_summary", ""),
            priority_actions=result.get("priority_actions", []),
        )
        _persist_lsta(
            req.session_id,
            f"四维诊断 Listing: {req.asin} ({req.marketplace})",
            (result.get("analysis") or "")[:2000],
            user_id=user_id,
            intent="analyze",
            latency_ms=int((time.time() - t0) * 1000),
            extra={
                "asin": req.asin,
                "marketplace": req.marketplace,
                "score": result.get("score"),
            },
        )
        return resp
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        logger.error("Listing 四维诊断失败: %s", e)
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.exception("Listing 四维诊断异常")
        raise HTTPException(status_code=500, detail=f"诊断过程出错: {e}")


def _extract_json_obj(raw: str) -> dict:
    text = (raw or "").strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start:end + 1])
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


@router.post("/deep-diagnostic", response_model=ListingDeepDiagnosticResponse, summary="Listing 子项深度诊断")
def deep_diagnostic(req: ListingDeepDiagnosticRequest):
    """先做本品自我诊断，再对每个竞品独立做 A/B/C/D/E 对比诊断。"""
    product = req.product_data
    current_listing = {
        "title": req.current_title or product.title,
        "bullet_points": req.current_bullet_points or product.bullet_points,
        "description": req.current_description or product.description,
        "search_terms": req.current_search_terms,
    }
    review_block = req.review_analysis.model_dump() if req.review_analysis else None

    def _product_payload(pd):
        return {
            "asin": pd.asin,
            "title": pd.title,
            "brand": pd.brand,
            "price": pd.price,
            "currency": pd.currency,
            "rating": pd.rating,
            "review_count": pd.review_count,
            "monthly_sales_text": getattr(pd, "monthly_sales_text", "") or "",
            "bsr_rank": pd.bsr_rank,
            "bullet_points": pd.bullet_points[:5],
            "description": (pd.description or "")[:900],
            "review_samples": [r.model_dump() for r in (pd.reviews or [])[:6]],
        }

    competitors = []
    for idx, cp in enumerate((req.competitor_products or [])[:5]):
        competitors.append({
            "label": chr(ord("A") + idx),
            "asin": cp.asin,
            "title": cp.title,
            "brand": cp.brand,
            "price": cp.price,
            "currency": cp.currency,
            "rating": cp.rating,
            "review_count": cp.review_count,
            "monthly_sales_text": getattr(cp, "monthly_sales_text", "") or "",
            "bsr_rank": cp.bsr_rank,
            "bullet_points": cp.bullet_points[:5],
            "description": (cp.description or "")[:800],
            "review_samples": [r.model_dump() for r in (cp.reviews or [])[:5]],
        })

    self_prompt = f"""
你是 Amazon Listing 自我诊断专家。请先只诊断本品，不要做竞品汇总。

诊断目标：
1. 检查本品最多五张图片与 Listing 标题、五点、描述是否一致。
2. 检查图片表达与评论反馈是否一致：评论中的优点/痛点是否被图片和文案覆盖。
3. 检查尺寸、品牌、颜色、材质、使用场景、核心卖点是否清楚。
4. 检查文案是否自然可读、是否有堆词、是否有图片未支撑的夸张表达。

必须只输出 JSON：
{{
  "self_diagnosis": {{
    "summary": "一句话总评",
    "strengths": ["..."],
    "weaknesses": ["..."],
    "suggestions": ["..."]
  }}
}}

本品基础信息：
{json.dumps(_product_payload(product), ensure_ascii=False)[:5000]}

当前待诊断 Listing：
{json.dumps(current_listing, ensure_ascii=False)[:5000]}

评论洞察：
{json.dumps(review_block, ensure_ascii=False)[:2500]}
""".strip()

    self_content: list[dict] = []
    for img in (product.images or [])[:5]:
        if img:
            self_content.append({"type": "image_url", "image_url": {"url": img}})
    self_content.append({"type": "text", "text": self_prompt})

    try:
        from admin.model_pool import model_pool
        raw_self = model_pool.call_llm(
            messages=[
                {"role": "system", "content": "你是严谨的 Amazon Listing 诊断专家，只输出 JSON。"},
                {"role": "user", "content": self_content},
            ],
            temperature=0.15,
            max_tokens=1400,
            timeout=150,
            _log_module="lsta_deep_diagnostic_self",
            preferred_model=req.model,
        )
        self_data = _extract_json_obj(raw_self)

        comp_sections: list[ListingCompetitorDiagnosticSection] = []
        comp_raws: list[str] = []
        for idx, cp in enumerate((req.competitor_products or [])[:5]):
            label = chr(ord("A") + idx)
            comp_prompt = f"""
你是 Amazon Listing 逐竞品对比诊断专家。现在只分析“本品 vs 竞品{label}”，不要把其他竞品混入结论。

必须对以下方向逐项对比：图片、品牌信任、评论反馈、Listing 五点/描述、标题、使用场景、销量/热度、产品潜力。
销量/热度规则：优先使用 monthly_sales_text（如 "50+ bought in past month"）。如果没有该字段，再用 BSR 排名、review_count、rating、价格做相对判断；不要编造销量。

必须只输出 JSON：
{{
  "summary": "本品 vs 竞品{label} 的一句话结论",
  "image_comparison": "图片呈现、主图/场景图/尺寸图/卖点图的差异",
  "brand_comparison": "品牌可信度与识别差异",
  "review_comparison": "评论优点/差评痛点差异",
  "listing_comparison": "五点和描述的清晰度、说服力、可读性差异",
  "title_comparison": "标题关键词、尺寸品牌场景表达差异",
  "scenario_comparison": "使用场景、人群、摆放/搭配表达差异",
  "sales_comparison": "优先基于 monthly_sales_text，没有则基于 BSR/review/rating/price",
  "own_advantages": ["本品相对竞品{label}的优势"],
  "own_disadvantages": ["本品相对竞品{label}的劣势"],
  "competitor_advantages": ["竞品{label}优势"],
  "competitor_disadvantages": ["竞品{label}劣势"],
  "suggestions": ["针对竞品{label}，本品 Listing/图片应如何改"]
}}

本品自我诊断：
{json.dumps(self_data.get("self_diagnosis") or {}, ensure_ascii=False)[:2500]}

本品数据：
{json.dumps(_product_payload(product), ensure_ascii=False)[:5000]}

当前待诊断 Listing：
{json.dumps(current_listing, ensure_ascii=False)[:5000]}

评论洞察：
{json.dumps(review_block, ensure_ascii=False)[:2000]}

竞品{label}数据：
{json.dumps(_product_payload(cp), ensure_ascii=False)[:5000]}
""".strip()
            comp_content: list[dict] = []
            for img in (product.images or [])[:5]:
                if img:
                    comp_content.append({"type": "image_url", "image_url": {"url": img}})
            for img in (cp.images or [])[:5]:
                if img:
                    comp_content.append({"type": "image_url", "image_url": {"url": img}})
            comp_content.append({"type": "text", "text": comp_prompt})
            raw_comp = model_pool.call_llm(
                messages=[
                    {"role": "system", "content": f"你是严谨的 Amazon 逐竞品对比专家，只输出本品 vs 竞品{label} 的 JSON。"},
                    {"role": "user", "content": comp_content},
                ],
                temperature=0.15,
                max_tokens=1800,
                timeout=180,
                _log_module=f"lsta_deep_diagnostic_comp_{label}",
                preferred_model=req.model,
            )
            comp_raws.append(raw_comp)
            comp_data = _extract_json_obj(raw_comp)
            comp_sections.append(ListingCompetitorDiagnosticSection.model_validate({
                **comp_data,
                "competitor_label": label,
                "competitor_asin": cp.asin,
                "competitor_title": cp.title,
                "competitor_brand": cp.brand,
                "competitor_image": (cp.images or [""])[0],
                "competitor_monthly_sales_text": getattr(cp, "monthly_sales_text", "") or "",
                "competitor_bsr_rank": cp.bsr_rank,
                "raw_output": raw_comp,
            }))

        return ListingDeepDiagnosticResponse(
            asin=req.asin,
            marketplace=req.marketplace,
            self_diagnosis=ListingDeepDiagnosticSection.model_validate(self_data.get("self_diagnosis") or {}),
            comparison_diagnosis=ListingDeepComparisonSection(
                summary=f"已完成 {len(comp_sections)} 个竞品的一一对比，请查看 A/B/C/D/E 选项卡。",
            ),
            competitor_diagnoses=comp_sections,
            raw_output=json.dumps({"self": raw_self, "competitors": comp_raws}, ensure_ascii=False),
        )
    except Exception as e:
        logger.exception("Listing 子项深度诊断失败")
        raise HTTPException(status_code=500, detail=f"深度诊断失败: {e}")


@router.post("/evaluate", response_model=ListingEvaluateResponse,
              summary="Listing 四维算法评判（COSMO/关键词/Rufus/IDQ）")
def evaluate_listing(req: ListingEvaluateRequest, user_id: Optional[str] = Depends(_optional_user)):
    """基于亚马逊 COSMO 关系覆盖、关键词覆盖、Rufus 语义覆盖、IDQ 语义完整性四维评判 Listing。"""
    t0 = time.time()
    try:
        result = listing_optimizer.evaluate(
            asin=req.asin,
            marketplace=req.marketplace,
            search_terms=req.search_terms,
            preferred_model=req.model,
            product_data=req.product_data,
        )
        resp = ListingEvaluateResponse(
            asin=req.asin,
            marketplace=req.marketplace,
            product=result["product"],
            scores=result.get("scores"),
            analysis=result.get("analysis"),
            overall_summary=result.get("overall_summary", ""),
            priority_actions=result.get("priority_actions", []),
            raw_output=result.get("raw_output", ""),
        )
        _persist_lsta(
            req.session_id,
            f"四维评判 Listing: {req.asin} ({req.marketplace})",
            json.dumps(
                (resp.scores.model_dump() if resp.scores else {}),
                ensure_ascii=False,
            )[:2000],
            user_id=user_id,
            intent="evaluate",
            latency_ms=int((time.time() - t0) * 1000),
            extra={
                "asin": req.asin,
                "marketplace": req.marketplace,
                "total_score": resp.scores.total if resp.scores else None,
            },
        )
        return resp
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        logger.error("Listing 四维评判失败: %s", e)
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.exception("Listing 四维评判异常")
        raise HTTPException(status_code=500, detail=f"四维评判出错: {e}")


@router.post("/refine", response_model=ListingRefineResponse, summary="根据用户反馈迭代修改 Listing")
def refine_listing(req: ListingRefineRequest, user_id: Optional[str] = Depends(_optional_user)):
    """接收用户修改意见，对现有 Listing 进行针对性调整。"""
    t0 = time.time()
    try:
        result = listing_optimizer.refine(
            asin=req.asin,
            marketplace=req.marketplace,
            current_title=req.current_title,
            current_bullet_points=req.current_bullet_points,
            current_description=req.current_description,
            current_search_terms=req.current_search_terms,
            user_feedback=req.user_feedback,
            preferred_model=req.model,
        )
        resp = ListingRefineResponse(
            asin=req.asin,
            marketplace=req.marketplace,
            optimized=result["optimized"],
        )
        _persist_lsta(
            req.session_id,
            f"迭代修改 Listing: {req.asin} - {req.user_feedback[:50]}",
            json.dumps(resp.optimized.model_dump(), ensure_ascii=False)[:2000],
            user_id=user_id,
            intent="refine",
            latency_ms=int((time.time() - t0) * 1000),
            extra={"asin": req.asin, "marketplace": req.marketplace, "feedback": req.user_feedback[:200]},
        )
        return resp
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        logger.error("Listing 迭代修改失败: %s", e)
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.exception("Listing 迭代修改异常")
        raise HTTPException(status_code=500, detail=f"迭代修改出错: {e}")


# ── 流量词分析 ──────────────────────────────

@router.post("/check-traffic-words", response_model=TrafficWordCheckResponse,
              summary="检查关键词是否为流量词")
def check_traffic_words(req: TrafficWordCheckRequest):
    """查询 ABA/SQR 报告判定关键词是否为流量词，并评估产品相关性。"""
    try:
        from LSTA.service.trafficWordService import traffic_word_service

        if req.words:
            check_result = traffic_word_service.check_words(req.words)
        elif req.title or req.bullet_points or req.description or req.search_terms:
            check_result = traffic_word_service.batch_check_listing(
                title=req.title,
                bullet_points=req.bullet_points,
                description=req.description,
                search_terms=req.search_terms,
                target_keywords=req.target_keywords,
            )
        else:
            return TrafficWordCheckResponse(
                word_analysis=WordAnalysis(),
                error="请提供 words 列表或 Listing 内容",
            )

        if req.product_title or req.product_category:
            product = ProductData(
                asin="", title=req.product_title, category=req.product_category,
            )
            from LSTA.models.listingState import OptimizedListing
            optimized = OptimizedListing(
                title=req.title,
                bullet_points=req.bullet_points,
                description=req.description,
                search_terms=req.search_terms,
            )
            word_analysis = listing_optimizer.analyze_traffic_words(
                optimized=optimized,
                product=product,
                target_keywords=req.target_keywords,
            )
        else:
            from LSTA.models.listingState import TrafficWordDetail
            traffic_words_raw = check_result.get("traffic_words", [])
            if isinstance(check_result, dict) and "is_traffic" in next(iter(check_result.values()), {}):
                traffic_details = []
                for word, info in check_result.items():
                    if info.get("is_traffic"):
                        aba = info.get("aba") or {}
                        sqr = info.get("sqr") or {}
                        traffic_details.append(TrafficWordDetail(
                            word=word,
                            aba_search_rank=aba.get("search_rank"),
                            aba_record_count=aba.get("record_count", 0),
                            sqr_total_impressions=sqr.get("search_query_count"),
                            sqr_record_count=sqr.get("record_count", 0),
                        ))
            else:
                traffic_details = []
                for tw in traffic_words_raw:
                    aba = tw.get("aba") or {}
                    sqr = tw.get("sqr") or {}
                    traffic_details.append(TrafficWordDetail(
                        word=tw["word"],
                        aba_search_rank=aba.get("search_rank"),
                        aba_record_count=aba.get("record_count", 0),
                        sqr_total_impressions=sqr.get("search_query_count"),
                        sqr_record_count=sqr.get("record_count", 0),
                    ))
            word_analysis = WordAnalysis(
                traffic_words=traffic_details,
                keyword_words=req.target_keywords,
                total_checked=check_result.get("total_words_checked", len(req.words)),
            )

        return TrafficWordCheckResponse(word_analysis=word_analysis)
    except Exception as e:
        logger.exception("流量词检查异常")
        raise HTTPException(status_code=500, detail=f"流量词检查出错: {e}")


@router.post("/apply-traffic-decisions", response_model=ListingRefineResponse,
              summary="应用用户对流量词的保留/替换决定")
def apply_traffic_decisions(req: TrafficWordDecisionRequest):
    """根据用户对弱相关流量词的决定，调用 LLM 微调 Listing。"""
    t0 = time.time()
    try:
        removals = [w for w, keep in req.decisions.items() if not keep]
        replacements = {w: req.replacements.get(w, "") for w in removals if req.replacements.get(w)}

        if not removals:
            from LSTA.models.listingState import OptimizedListing
            return ListingRefineResponse(
                asin=req.asin, marketplace=req.marketplace,
                optimized=OptimizedListing(
                    title=req.current_title,
                    bullet_points=req.current_bullet_points,
                    description=req.current_description,
                    search_terms=req.current_search_terms,
                ),
            )

        feedback_parts = ["请根据以下流量词决定修改 Listing："]
        for w in removals:
            replacement = replacements.get(w)
            if replacement:
                feedback_parts.append(f"- 将「{w}」替换为「{replacement}」")
            else:
                feedback_parts.append(f"- 移除或减少「{w}」的使用（该词与产品相关性不强）")
        feedback = "\n".join(feedback_parts)

        result = listing_optimizer.refine(
            asin=req.asin,
            marketplace=req.marketplace,
            current_title=req.current_title,
            current_bullet_points=req.current_bullet_points,
            current_description=req.current_description,
            current_search_terms=req.current_search_terms,
            user_feedback=feedback,
            preferred_model=req.model,
        )

        from LSTA.models.listingState import ListingRefineResponse as LRR
        resp = ListingRefineResponse(
            asin=req.asin, marketplace=req.marketplace,
            optimized=result["optimized"],
        )
        _persist_lsta(
            req.session_id,
            f"流量词决策调整: {req.asin}",
            f"移除: {removals}, 替换: {replacements}",
            intent="traffic_decision",
            latency_ms=int((time.time() - t0) * 1000),
        )
        return resp
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("流量词决策调整异常")
        raise HTTPException(status_code=500, detail=f"调整出错: {e}")


LISTING_COLLECTION = "listing"


@router.post("/embed", response_model=ListingEmbedResponse, summary="将 Listing 入库 Milvus")
def embed_listing(req: ListingEmbedRequest):
    """将优化/修改后的 Listing 数据 embedding 并存入 Milvus listing 集合。"""
    if not req.title.strip():
        raise HTTPException(status_code=400, detail="标题不能为空")

    bullets_text = "\n".join(f"- {bp}" for bp in req.bullet_points if bp.strip())
    full_text = (
        f"ASIN: {req.asin}\n"
        f"Marketplace: {req.marketplace}\n"
        f"Title: {req.title}\n"
        f"Bullet Points:\n{bullets_text}\n"
        f"Description: {req.description}\n"
        f"Search Terms: {req.search_terms}"
    )

    try:
        from LMA.service.embeddingService import embedding_service
        from LMA.service.milvusService import milvus_service

        milvus_service.ensure_collection(LISTING_COLLECTION)

        vectors = embedding_service.embedding_texts([full_text])
        if not vectors:
            raise RuntimeError("Embedding 生成失败")

        rows = [{
            "text": full_text,
            "embedding": vectors[0],
            "source_type": "listing",
            "chunk_index": 0,
            "file_name": f"{req.asin}_{req.marketplace}",
        }]
        result = milvus_service.insert_rows(rows, collection_name=LISTING_COLLECTION)

        if result.get("success"):
            return ListingEmbedResponse(
                success=True,
                message=f"ASIN {req.asin} Listing 已入库",
                collection=LISTING_COLLECTION,
                insert_count=result.get("insert_count", 1),
            )
        else:
            raise RuntimeError(result.get("error", "插入失败"))

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Listing 入库 Milvus 失败")
        raise HTTPException(status_code=500, detail=f"入库失败: {e}")


# ── 领星 ERP 提交 ──────────────────────────────

@router.get("/lingxing/status", summary="领星 ERP 连接状态")
def lingxing_status():
    return {"configured": lingxing_service.configured}


@router.post("/submit-to-lingxing", response_model=LingxingSubmitResponse, summary="提交 Listing 到领星 ERP")
def submit_to_lingxing(req: LingxingSubmitRequest):
    """将优化后的 Listing 数据推送到领星 ERP。"""
    if not lingxing_service.configured:
        raise HTTPException(
            status_code=503,
            detail="领星 ERP 未配置：请在 .env 中设置 LINGXING_APP_ID 和 LINGXING_APP_SECRET",
        )
    try:
        result = lingxing_service.submit_listing(
            asin=req.asin,
            marketplace=req.marketplace,
            title=req.title,
            bullet_points=req.bullet_points,
            description=req.description,
            search_terms=req.search_terms,
        )
        return LingxingSubmitResponse(
            success=True,
            message=f"ASIN {req.asin} Listing 已提交到领星",
            detail=result.get("data"),
        )
    except Exception as e:
        logger.exception("提交到领星失败")
        raise HTTPException(status_code=502, detail=f"提交领星失败: {e}")


# ── 后台任务 ──────────────────────────────


def _run_optimize_task(req: ListingOptimizeRequest, task_id: Optional[str] = None, user_id: Optional[str] = None) -> dict:
    """在后台线程中执行优化（供 task_store 调用）。

    支持多候选：当 req.variant_count>1 时走 optimize_multi 流程，同时把阶段性
    进度通过 task_store.update_partial 推送给前端，以支持"边生成边展示"。
    """
    t0 = time.time()
    overrides: dict[str, str] | None = None
    if req.prompt_overrides:
        overrides = {k: v for k, v in req.prompt_overrides.items() if v and v.strip()}
        if not overrides:
            overrides = None
    custom_params_dict: dict | None = None
    if req.custom_params:
        custom_params_dict = req.custom_params.model_dump(exclude_none=True)

    # 颜色兜底：前端未传时从 leang_product_info.colour 查一次，确保优化 prompt 能拿到
    color_for_optimize = (req.color or "").strip()
    if not color_for_optimize:
        try:
            from LSTA.service.productDimService import query_product_color
            color_for_optimize = query_product_color(req.asin)
        except Exception as exc:
            logger.warning("优化任务: 查询产品颜色失败（忽略）: %s", exc)
            color_for_optimize = ""

    # 三维诊断兜底：前端未传时自动查询，用于候选加权选最优
    tri_dim_for_optimize = req.tri_dim
    if tri_dim_for_optimize is None and req.variant_count and req.variant_count > 1:
        try:
            tri_dim_for_optimize = _query_tri_dim(req.asin)
        except Exception as exc:
            logger.warning("优化任务: 兜底查询三维诊断失败（忽略）: %s", exc)
            tri_dim_for_optimize = None

    sp_ad_rows: list[dict] = []
    try:
        if req.sp_ad_insights:
            sp_ad_rows = [x.model_dump() for x in req.sp_ad_insights]
        else:
            sp_payload = sp_ad_insight_service.query(asin=req.asin, days=60, limit=30)
            sp_ad_rows = _sp_ad_insight_items(sp_payload.get("items", []))
    except Exception as exc:
        logger.warning("优化任务: SP 广告词洞察读取失败（忽略）: %s", exc)
        sp_ad_rows = []

    sp_words, sp_prompt = sp_ad_insight_service.top_words_for_prompt(sp_ad_rows, limit=20)
    merged_kw = list(req.target_keywords or [])
    seen_kw = {k.strip().lower() for k in merged_kw if k and k.strip()}
    for word in sp_words:
        low = word.strip().lower()
        if low and low not in seen_kw:
            merged_kw.append(word.strip())
            seen_kw.add(low)

    target_audience_for_optimize = req.target_audience
    if sp_prompt:
        ad_block = (
            "\n\n[AK SP广告真实投放洞察]\n"
            "以下词来自AK店铺领星SP广告数据。high_conversion词优先自然覆盖到标题/五点/Search Terms；"
            "high_click_no_order词不要机械堆砌，应检查并补强Listing承接；"
            "high_impression_low_ctr词仅在强相关时使用。\n"
            f"{sp_prompt}"
        )
        target_audience_for_optimize = (target_audience_for_optimize or "") + ad_block

    common_kwargs = dict(
        asin=req.asin,
        marketplace=req.marketplace,
        target_keywords=merged_kw,
        target_audience=target_audience_for_optimize,
        language=req.language,
        optimize_strategy=req.optimize_strategy.value,
        preferred_model=req.model,
        prompt_overrides=overrides,
        product_data=req.product_data,
        optimize_sections=req.optimize_sections,
        competitor_products=req.competitor_products,
        custom_params=custom_params_dict,
        enable_fab=req.enable_fab,
        skip_traffic_analysis=True,
        review_analysis=req.review_analysis,
        color=color_for_optimize,
    )

    if req.variant_count and req.variant_count > 1:
        # 构造进度回调：将 optimize_multi 的阶段性产出写入 task_store
        def _on_progress(payload: dict):
            if task_id:
                task_store.update_partial(task_id, payload)

        result = listing_optimizer.optimize_multi(
            variant_count=req.variant_count,
            preferred_eval_model=req.eval_model,
            on_progress=_on_progress,
            tri_dim=tri_dim_for_optimize,
            **common_kwargs,
        )
    else:
        result = listing_optimizer.optimize(**common_kwargs)

    resp = ListingOptimizeResponse(
        asin=req.asin,
        marketplace=req.marketplace,
        original=result["original"],
        optimized=result["optimized"],
        variants=result.get("variants", []),
        best_variant_index=result.get("best_variant_index"),
        tri_dim_hit=result.get("tri_dim_hit"),
    )
    latency = int((time.time() - t0) * 1000)
    base_extra = {"asin": req.asin, "marketplace": req.marketplace}
    if resp.variants and len(resp.variants) > 1:
        var_mem_ids: List[Optional[int]] = []
        for idx, v in enumerate(resp.variants):
            vid = _persist_lsta(
                req.session_id,
                f"优化 Listing (候选{idx+1}): {req.asin} ({req.marketplace})",
                json.dumps(v.listing.model_dump(), ensure_ascii=False)[:2000],
                user_id=user_id,
                intent="optimize",
                latency_ms=latency,
                extra={**base_extra, "variant_index": idx, "variant_score": v.composite_score},
            )
            var_mem_ids.append(vid)
        resp.variant_memory_ids = var_mem_ids
        best_idx = result.get("best_variant_index") or 0
        resp.memory_id = var_mem_ids[best_idx] if var_mem_ids else None
    else:
        mem_id = _persist_lsta(
            req.session_id,
            f"优化 Listing: {req.asin} ({req.marketplace})",
            json.dumps(resp.optimized.model_dump(), ensure_ascii=False)[:2000],
            user_id=user_id,
            intent="optimize",
            latency_ms=latency,
            extra=base_extra,
        )
        resp.memory_id = mem_id
    return resp.model_dump()


def _run_analyze_task(req: ListingAnalyzeRequest, user_id: Optional[str] = None) -> dict:
    """在后台线程中执行诊断（供 task_store 调用）。"""
    t0 = time.time()
    result = listing_optimizer.analyze(
        asin=req.asin,
        marketplace=req.marketplace,
        search_terms=req.search_terms,
        preferred_model=req.model,
        product_data=req.product_data,
    )
    resp = ListingAnalyzeResponse(
        asin=req.asin,
        marketplace=req.marketplace,
        product=result["product"],
        analysis=result["analysis"],
        score=result.get("score"),
        scores=result.get("scores"),
        evaluate_analysis=result.get("evaluate_analysis"),
        overall_summary=result.get("overall_summary", ""),
        priority_actions=result.get("priority_actions", []),
    )
    _persist_lsta(
        req.session_id,
        f"四维诊断 Listing: {req.asin} ({req.marketplace})",
        (result.get("analysis") or "")[:2000],
        user_id=user_id,
        intent="analyze",
        latency_ms=int((time.time() - t0) * 1000),
        extra={
            "asin": req.asin,
            "marketplace": req.marketplace,
            "score": result.get("score"),
        },
    )
    return resp.model_dump()


def _run_competitor_task(req: CompetitorDiscoveryRequest) -> dict:
    """在后台线程中执行竞品发现（通过 Amazon 搜索）。"""
    resp = discover_competitors(
        asin=req.asin,
        marketplace=req.marketplace,
        price_tolerance=req.price_tolerance,
        max_results=req.max_results,
        with_details=req.with_details,
        product_data=req.product_data,
        color=req.color or None,
        filter_by_color=req.filter_by_color,
        filter_by_size=req.filter_by_size,
        filter_by_style=req.filter_by_style,
        min_review_count=req.min_review_count,
    )
    return resp.model_dump()


def _run_market_analysis_task(req: MarketAnalysisRequest) -> dict:
    """在后台线程中执行市场分析（通过 Amazon 搜索方向词）。"""
    resp = market_analysis_service.analyze(
        keyword=req.keyword,
        marketplace=req.marketplace,
        max_results=req.max_results,
        max_pages=req.max_pages,
        with_details=req.with_details,
        model=req.model,
    )
    return resp.model_dump()


def _run_review_analysis_task(req) -> dict:
    """在后台线程中执行评论分析。"""
    result = review_analysis_service.analyze(
        reviews=req.reviews,
        product_title=req.product_title,
        model=req.model,
    )
    from LSTA.models.listingState import ReviewAnalysisResponse
    resp = ReviewAnalysisResponse(
        asin=req.asin,
        marketplace=req.marketplace,
        review_count=len(req.reviews),
        analysis=result,
    )
    return resp.model_dump()


def _run_fetch_product_task(req: FetchProductRequest, task_id: str | None = None) -> dict:
    """后台线程：获取产品信息 + 三维诊断 + 流量词 + 评论分析（并行执行）。"""
    import concurrent.futures

    product = listing_optimizer.fetch(asin=req.asin, marketplace=req.marketplace)

    # 产品数据已就绪，立即写入 partial，让前端提前渲染，无需等后续并行任务完成
    if task_id:
        try:
            task_store.update_partial(task_id, {"product": product.model_dump()})
        except Exception:
            pass

    tri_dim = None
    traffic_items: list[TrafficWordItem] = []
    sp_ad_items: list[dict] = []
    review_result = None

    def _td():
        try:
            return _query_tri_dim(req.asin)
        except Exception as exc:
            logger.warning("三维诊断查询失败: %s", exc)
            return None

    def _tw():
        try:
            from LSTA.service.trafficWordService import traffic_word_service
            return traffic_word_service.batch_check_listing(
                title=product.title,
                bullet_points=product.bullet_points,
                description=product.description,
                search_terms="",
                target_keywords=[],
            )
        except Exception as exc:
            logger.warning("流量词查询失败: %s", exc)
            return None

    def _ra():
        try:
            if not mws_reviews:
                return None
            return review_analysis_service.analyze(
                reviews=mws_reviews,
                product_title=product.title,
            )
        except Exception as exc:
            logger.warning("评论分析失败（不影响主流程）: %s", exc)
            return None

    def _color():
        try:
            from LSTA.service.productDimService import query_product_color
            return query_product_color(req.asin)
        except Exception as exc:
            logger.warning("产品颜色查询失败: %s", exc)
            return ""

    def _spad():
        try:
            payload = sp_ad_insight_service.query(asin=req.asin, days=60, limit=60)
            return payload.get("items", [])
        except Exception as exc:
            logger.warning("SP 广告词洞察查询失败: %s", exc)
            return []

    def _mws_reviews():
        try:
            return mws_review_service.query_reviews_with_title(
                asin=req.asin,
                marketplace=req.marketplace,
                limit=100,
            )
        except Exception as exc:
            logger.warning("MWS 评论读取失败: %s", exc)
            return "", []

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        tri_future = pool.submit(_td)
        tw_future = pool.submit(_tw)
        color_future = pool.submit(_color)
        spad_future = pool.submit(_spad)
        mws_future = pool.submit(_mws_reviews)
        tri_dim = tri_future.result(timeout=180)
        tw_result = tw_future.result(timeout=180)
        db_color = color_future.result(timeout=30) or ""
        sp_ad_items = spad_future.result(timeout=60) or []
        mws_title, mws_reviews = mws_future.result(timeout=120)

    if mws_reviews:
        product.reviews = mws_reviews
        if mws_title and not product.title:
            product.title = mws_title
        review_result = _ra()

    if tw_result:
        for tw in tw_result.get("traffic_words", []):
            aba = tw.get("aba") or {}
            sqr = tw.get("sqr") or {}
            has_aba = bool(aba)
            has_sqr = bool(sqr)
            source = "both" if has_aba and has_sqr else ("aba" if has_aba else "sqr")
            traffic_items.append(TrafficWordItem(
                word=tw["word"],
                aba_search_rank=aba.get("search_rank"),
                sqr_total_impressions=sqr.get("search_query_count"),
                source=source,
            ))

    if traffic_items:
        try:
            words_str = ", ".join(item.word for item in traffic_items[:60])
            relevance_map = listing_optimizer.assess_traffic_relevance(
                traffic_words=words_str,
                product=product,
            )
            for item in traffic_items:
                rel_info = relevance_map.get(item.word.lower(), {})
                item.relevance = rel_info.get("relevance", "unknown")
                item.reason = rel_info.get("reason", "")
        except Exception as exc:
            logger.warning("流量词相关性判定失败: %s", exc)

    existing_words = {item.word.lower() for item in traffic_items}
    for item in sp_ad_items:
        word = str(item.get("word_text") or "").strip().lower()
        if not word or word in existing_words:
            continue
        existing_words.add(word)
        traffic_items.append(TrafficWordItem(
            word=word,
            aba_search_rank=None,
            sqr_total_impressions=int(item.get("impressions") or 0),
            source="sp_ads",
            relevance="clear" if item.get("insight_type") == "high_conversion" else "unknown",
            reason=item.get("reason") or item.get("insight_type") or "AK SP ad insight",
        ))

    return FetchDiagnosticsResponse(
        product=product,
        tri_dim=tri_dim,
        traffic_words=traffic_items,
        traffic_word_count=len(traffic_items),
        sp_ad_insights=_sp_ad_insight_items(sp_ad_items),
        sp_ad_insight_count=len(sp_ad_items),
        review_analysis=review_result,
        db_color=db_color,
    ).model_dump()


def _run_fetch_reviews_task(req: FetchProductRequest) -> dict:
    """后台线程：从领星 MWS 评论表读取产品评论，不走网页抓取。"""
    title, reviews = mws_review_service.query_reviews_with_title(
        asin=req.asin,
        marketplace=req.marketplace,
        limit=100,
    )
    return {
        "title": title,
        "reviews": [r.model_dump() for r in reviews],
        "source": "dwd_lingxing_mws_reviews_incr",
    }


@router.post("/task/submit", response_model=TaskSubmitResponse, summary="提交后台任务")
def submit_task(req: TaskSubmitRequest, user_id: Optional[str] = Depends(_optional_user)):
    """提交优化/诊断任务到后台执行，立即返回 task_id。"""
    if req.action == "optimize":
        if not req.optimize_params:
            raise HTTPException(status_code=400, detail="optimize_params 不能为空")
        params = req.optimize_params
        snapshot = {"asin": params.asin, "marketplace": params.marketplace}
        task_id = task_store.create(action="optimize", params_snapshot=snapshot)
        # 闭包把 task_id / user_id 带给 _run_optimize_task，以便其把实时进度写回 task_store 并记录操作人
        _tid = task_id
        _uid = user_id
        task_store.run_in_thread(task_id, lambda: _run_optimize_task(params, _tid, _uid))
    elif req.action == "analyze":
        if not req.analyze_params:
            raise HTTPException(status_code=400, detail="analyze_params 不能为空")
        params = req.analyze_params
        snapshot = {"asin": params.asin, "marketplace": params.marketplace}
        task_id = task_store.create(action="analyze", params_snapshot=snapshot)
        _uid = user_id
        task_store.run_in_thread(task_id, lambda: _run_analyze_task(params, _uid))
    elif req.action == "discover_competitors":
        if not req.competitor_params:
            raise HTTPException(status_code=400, detail="competitor_params 不能为空")
        cp = req.competitor_params
        snapshot = {"asin": cp.asin, "marketplace": cp.marketplace}
        task_id = task_store.create(action="discover_competitors", params_snapshot=snapshot)
        task_store.run_in_thread(task_id, lambda: _run_competitor_task(cp))
    elif req.action == "market_analysis":
        if not req.market_analysis_params:
            raise HTTPException(status_code=400, detail="market_analysis_params 不能为空")
        ma = req.market_analysis_params
        snapshot = {"asin": ma.keyword, "marketplace": ma.marketplace}
        task_id = task_store.create(action="market_analysis", params_snapshot=snapshot)
        task_store.run_in_thread(task_id, lambda: _run_market_analysis_task(ma))
    elif req.action == "review_analysis":
        if not req.review_analysis_params:
            raise HTTPException(status_code=400, detail="review_analysis_params 不能为空")
        ra = req.review_analysis_params
        snapshot = {"asin": ra.asin, "marketplace": ra.marketplace}
        task_id = task_store.create(action="review_analysis", params_snapshot=snapshot)
        task_store.run_in_thread(task_id, lambda: _run_review_analysis_task(ra))
    elif req.action == "fetch_product":
        if not req.fetch_params:
            raise HTTPException(status_code=400, detail="fetch_params 不能为空")
        fp = req.fetch_params
        snapshot = {"asin": fp.asin, "marketplace": fp.marketplace}
        task_id = task_store.create(action="fetch_product", params_snapshot=snapshot)
        _fp_tid = task_id
        task_store.run_in_thread(task_id, lambda: _run_fetch_product_task(fp, _fp_tid))
    elif req.action == "fetch_reviews":
        if not req.fetch_params:
            raise HTTPException(status_code=400, detail="fetch_params 不能为空")
        fr = req.fetch_params
        snapshot = {"asin": fr.asin, "marketplace": fr.marketplace}
        task_id = task_store.create(action="fetch_reviews", params_snapshot=snapshot)
        task_store.run_in_thread(task_id, lambda: _run_fetch_reviews_task(fr))
    else:
        raise HTTPException(status_code=400, detail=f"不支持的 action: {req.action}")

    return TaskSubmitResponse(task_id=task_id)


@router.get("/task/{task_id}", response_model=TaskStatusResponse, summary="查询任务状态")
def get_task_status(task_id: str):
    """轮询任务状态，completed 时包含完整结果。"""
    entry = task_store.get(task_id)
    if not entry:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return task_store.to_dict(entry)


@router.get("/tasks", response_model=TaskListResponse, summary="获取所有任务列表")
def list_tasks():
    """获取当前所有任务（含进行中和已完成）。"""
    return TaskListResponse(tasks=task_store.list_tasks())


@router.delete("/task/{task_id}", summary="删除任务")
def delete_task(task_id: str):
    """手动删除/清理指定任务。"""
    if task_store.delete(task_id):
        return {"success": True, "message": f"任务 {task_id} 已删除"}
    raise HTTPException(status_code=404, detail="任务不存在")


# ── 用户反馈（点赞/差劲/评论 → llm_memory） ─────────


@router.post(
    "/memory/feedback",
    response_model=MemoryFeedbackResponse,
    summary="提交用户反馈（点赞/差劲/评论）到 llm_memory",
)
def submit_memory_feedback(req: MemoryFeedbackRequest, user_id: Optional[str] = Depends(_optional_user)):
    """更新 llm_memory 表的 user_liked / user_disliked / user_comment 字段。"""
    if req.liked is None and req.disliked is None and req.comment is None:
        raise HTTPException(status_code=400, detail="liked / disliked / comment 至少传一个")
    try:
        from Base.Service.memoryDbService import memory_db
        # 把操作人记录在 extra 扩展字段，可查是谁点赞/评论
        ok = memory_db.update_feedback(
            req.memory_id,
            liked=req.liked,
            disliked=req.disliked,
            comment=req.comment,
            feedback_by=user_id,
        )
        if not ok:
            raise HTTPException(status_code=404, detail=f"记忆 id={req.memory_id} 不存在或未更新")
        return MemoryFeedbackResponse(success=True, memory_id=req.memory_id, message="已记录")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("提交反馈失败")
        raise HTTPException(status_code=500, detail=f"提交反馈失败: {e}")


# ── 搜索词相关性推荐 ─────────────────────────


@router.post(
    "/search-term-recommend",
    response_model=SearchTermRecommendResponse,
    summary="搜索词相关性推荐",
)
def search_term_recommend(req: SearchTermRecommendRequest):
    """根据 ASIN 查询 MSKU 对应的搜索词相关性结果。

    流程: ASIN → leang_product_info (msku, store_name) → 共享目录 Excel → search_term + relevance
    """
    try:
        result = search_term_recommend_service.recommend(
            asin=req.asin,
            relevance_filter=req.relevance_filter,
        )
        return SearchTermRecommendResponse(**result)
    except Exception as e:
        logger.error("搜索词推荐失败 (asin=%s): %s", req.asin, e, exc_info=True)
        raise HTTPException(status_code=502, detail=f"搜索词推荐服务异常: {e}")


@router.post(
    "/sqr-search-volume",
    response_model=SqrSearchVolumeResponse,
    summary="按需查询单个搜索词 SQR 搜索量（悬停用）",
)
def sqr_search_volume(req: SqrSearchVolumeRequest):
    """对单个词查询 sqr_report 中 search_query_count 汇总，并返回 A~F 档位。

    设计为**单条**查询 + 服务端 TTL 缓存，避免对超大表做批量或模糊扫描。
    """
    try:
        payload = sqr_search_volume_service.query_one(req.term)
        return SqrSearchVolumeResponse(**payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        logger.warning("SQR 搜索量查询失败: %s", e)
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.exception("SQR 搜索量查询异常")
        raise HTTPException(status_code=500, detail=f"查询异常: {e}")


@router.post(
    "/sqr-search-volumes",
    response_model=SqrSearchVolumesResponse,
    summary="批量查询 SQR 搜索量（当前列表筛选用）",
)
def sqr_search_volumes(req: SqrSearchVolumesRequest):
    """单次分组 SQL 查询多词搜索量，每请求最多 500 个不重复词，结果写入进程缓存。"""
    if not req.terms:
        return SqrSearchVolumesResponse(volumes={})
    if len(req.terms) > 500:
        raise HTTPException(status_code=400, detail="单次最多查询 500 个搜索词")
    try:
        raw = sqr_search_volume_service.query_many(req.terms)
        return SqrSearchVolumesResponse(
            volumes={k: SqrSearchVolumeResponse.model_validate(v) for k, v in raw.items()},
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        logger.warning("SQR 批量搜索量查询失败: %s", e)
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.exception("SQR 批量搜索量查询异常")
        raise HTTPException(status_code=500, detail=f"查询异常: {e}")


# ═══════════════════════════════════════════════
# 评论分析
# ═══════════════════════════════════════════════

@router.post(
    "/review-analysis",
    response_model=ReviewAnalysisResponse,
    summary="评论分析（提取痛点/卖点/核心特点）",
)
def review_analysis(req: ReviewAnalysisRequest):
    """通过 LLM 分析用户评论，提取痛点、卖点和核心特点。"""
    if not req.reviews:
        raise HTTPException(status_code=400, detail="评论列表不能为空")
    if len(req.reviews) > 100:
        raise HTTPException(status_code=400, detail="单次最多分析 100 条评论")
    try:
        result = review_analysis_service.analyze(
            reviews=req.reviews,
            product_title=req.product_title,
            model=req.model,
        )
        return ReviewAnalysisResponse(
            asin=req.asin,
            marketplace=req.marketplace,
            review_count=len(req.reviews),
            analysis=result,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("评论分析异常")
        raise HTTPException(status_code=500, detail=f"分析失败: {e}")


# ═══════════════════════════════════════════════
# 竞品发现
# ═══════════════════════════════════════════════

@router.post(
    "/discover-competitors",
    response_model=CompetitorDiscoveryResponse,
    summary="竞品发现（同步，亦可走 /task/submit action=discover_competitors）",
)
def discover_competitors_sync(req: CompetitorDiscoveryRequest):
    """通过 Amazon 搜索发现竞品（价格/评论数/尺寸/款式四维过滤 + 排除自有 ASIN）。"""
    try:
        return discover_competitors(
            asin=req.asin,
            marketplace=req.marketplace,
            price_tolerance=req.price_tolerance,
            max_results=req.max_results,
            with_details=req.with_details,
            product_data=req.product_data,
            color=req.color or None,
            filter_by_color=req.filter_by_color,
            filter_by_size=req.filter_by_size,
            filter_by_style=req.filter_by_style,
            min_review_count=req.min_review_count,
        )
    except Exception as e:
        logger.exception("竞品发现异常")
        raise HTTPException(status_code=500, detail=f"竞品发现失败: {e}")


# ═══════════════════════════════════════════════
# 市场分析
# ═══════════════════════════════════════════════

@router.post(
    "/market-analysis",
    response_model=MarketAnalysisResponse,
    summary="市场分析（输入方向词，抓取 Amazon 样本并生成市场洞察）",
)
def market_analysis(req: MarketAnalysisRequest):
    """根据用户输入的市场方向自动搜索 Amazon，并聚合容量、品牌、痛点、趋势和机会。"""
    try:
        return market_analysis_service.analyze(
            keyword=req.keyword,
            marketplace=req.marketplace,
            max_results=req.max_results,
            max_pages=req.max_pages,
            with_details=req.with_details,
            model=req.model,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("市场分析异常")
        raise HTTPException(status_code=500, detail=f"市场分析失败: {e}")


# ═══════════════════════════════════════════════
# SP 广告投放策略与时间反馈
# ═══════════════════════════════════════════════

@router.post("/ad-strategy/analyze", summary="SP 广告投放策略分析（含时间趋势与动作反馈）")
def ad_strategy_analyze(req: AdStrategyAnalyzeRequest):
    try:
        return ad_strategy_service.analyze(
            asin=req.asin or "",
            sku=req.sku or "",
            store_name=req.store_name or "",
            country_code=req.country_code or "",
            days=req.days,
            feedback_days=req.feedback_days,
            limit=req.limit,
        )
    except Exception as e:
        logger.exception("广告投放策略分析失败")
        raise HTTPException(status_code=500, detail=f"广告投放策略分析失败: {e}")


@router.post("/ad-strategy/actions", summary="记录 SP 广告投放动作")
def create_ad_strategy_action(req: AdStrategyActionCreateRequest, user_id: Optional[str] = Depends(_optional_user)):
    try:
        return ad_strategy_service.create_action(req.model_dump(), operator=user_id or "")
    except Exception as e:
        logger.exception("记录广告投放动作失败")
        raise HTTPException(status_code=500, detail=f"记录广告投放动作失败: {e}")


@router.post("/ad-strategy/feedback", summary="查询 SP 广告动作前后反馈")
def ad_strategy_feedback(req: AdStrategyFeedbackRequest):
    try:
        return ad_strategy_service.feedback(
            action_id=req.action_id,
            asin=req.asin or "",
            days=req.days,
        )
    except Exception as e:
        logger.exception("广告动作反馈查询失败")
        raise HTTPException(status_code=500, detail=f"广告动作反馈查询失败: {e}")


# ═══════════════════════════════════════════════
# Listing 优化确认入库记录
# ═══════════════════════════════════════════════

@router.post("/listing-optimize-records", summary="确认 Listing 优化结果入库")
def create_listing_optimize_record(
    req: ListingOptimizeRecordCreateRequest,
    user_id: Optional[str] = Depends(_optional_user),
):
    try:
        return listing_optimize_record_service.create(req.model_dump(), operator=user_id or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Listing 优化记录入库失败")
        raise HTTPException(status_code=500, detail=f"Listing 优化记录入库失败: {e}")


@router.post("/listing-optimize-records/list", summary="查询 Listing 优化入库记录")
def list_listing_optimize_records(req: ListingOptimizeRecordQueryRequest):
    try:
        return listing_optimize_record_service.list(
            asin=req.asin or "",
            marketplace=req.marketplace or "",
            limit=req.limit,
        )
    except Exception as e:
        logger.exception("Listing 优化记录查询失败")
        raise HTTPException(status_code=500, detail=f"Listing 优化记录查询失败: {e}")


@router.post("/listing-optimize-records/detail", summary="查询 Listing 优化入库记录详情")
def detail_listing_optimize_record(req: ListingOptimizeRecordDetailRequest):
    try:
        return listing_optimize_record_service.detail(req.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Listing 优化记录详情查询失败")
        raise HTTPException(status_code=500, detail=f"Listing 优化记录详情查询失败: {e}")


@router.post("/listing-optimize-records/remark", summary="修改 Listing 优化入库记录备注")
def update_listing_optimize_record_remark(
    req: ListingOptimizeRecordUpdateRemarkRequest,
    user_id: Optional[str] = Depends(_optional_user),
):
    try:
        return listing_optimize_record_service.update_remark(req.id, req.remark, operator=user_id or "")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Listing 优化记录备注修改失败")
        raise HTTPException(status_code=500, detail=f"Listing 优化记录备注修改失败: {e}")


@router.post("/listing-optimize-records/store", summary="修改 Listing 优化入库记录店铺")
def update_listing_optimize_record_store(
    req: ListingOptimizeRecordUpdateStoreRequest,
    user_id: Optional[str] = Depends(_optional_user),
):
    try:
        return listing_optimize_record_service.update_store(
            req.id,
            req.store_name,
            country_code=req.country_code,
            sku=req.sku,
            operator=user_id or "",
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Listing 优化记录店铺修改失败")
        raise HTTPException(status_code=500, detail=f"Listing 优化记录店铺修改失败: {e}")


@router.post("/listing-optimize-records/store-options", summary="查询 Listing 优化记录可选店铺")
def listing_optimize_record_store_options(req: ListingOptimizeRecordStoreOptionsRequest):
    try:
        return listing_optimize_record_service.store_options(req.asin)
    except Exception as e:
        logger.exception("Listing 优化记录店铺选项查询失败")
        raise HTTPException(status_code=500, detail=f"Listing 优化记录店铺选项查询失败: {e}")


@router.post("/listing-optimize-records/delete", summary="删除 Listing 优化入库记录")
def delete_listing_optimize_record(req: ListingOptimizeRecordDeleteRequest):
    try:
        return listing_optimize_record_service.delete(req.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Listing 优化记录删除失败")
        raise HTTPException(status_code=500, detail=f"Listing 优化记录删除失败: {e}")


# ═══════════════════════════════════════════════
# 批量翻译（hover 中文翻译用）
# ═══════════════════════════════════════════════

# 翻译固定走模型池中的 gpt-4o-mini（与主优化模型解耦）
_TRANSLATE_MODEL_ID = "gpt-4o-mini"


def _model_pool_entry_by_model_id(model_pool, model_id: str):
    """在已加载的 primary + standby 中按 model 名称查找条目。"""
    seq: list = []
    if getattr(model_pool, "primary", None):
        seq.append(model_pool.primary)
    seq.extend(getattr(model_pool, "standby", []) or [])
    for c in seq:
        if c and c.get("model") == model_id:
            return c
    return None


@router.post(
    "/translate",
    response_model=TranslateResponse,
    summary="批量翻译文本到目标语言（hover 中文翻译用）",
)
def translate_texts(req: TranslateRequest):
    """将一组英文/任意语言文本批量翻译为目标语言（默认简体中文）。

    - 要求模型严格按 JSON 数组返回，长度与 texts 对齐。
    - 单次最多 20 条，超长文本（>2000 字）直接截断提示词。
    """
    texts = [t for t in (req.texts or []) if isinstance(t, str)]
    if not texts:
        return TranslateResponse(translations=[], target_lang=req.target_lang)
    if len(texts) > 20:
        raise HTTPException(status_code=400, detail="单次最多翻译 20 条文本")

    from admin.model_pool import model_pool

    entry = _model_pool_entry_by_model_id(model_pool, _TRANSLATE_MODEL_ID)
    if not entry:
        raise HTTPException(
            status_code=503,
            detail=f"翻译固定使用 {_TRANSLATE_MODEL_ID}，但当前 model_pool 中未配置该模型，请在 model_pool.json 中加入后再试",
        )
    translate_preferred = f"{entry['provider']}:{entry['model']}"

    target = req.target_lang or "zh-CN"
    lang_name = "简体中文" if target.lower().startswith("zh") else target

    numbered = "\n".join(f"[{i}] {t}" for i, t in enumerate(texts))
    sys_prompt = (
        f"你是资深的亚马逊 Listing 翻译助手，严格把用户给的每条文本翻译为{lang_name}。\n"
        "规则：\n"
        "1. 保留原文语气和卖点，但用自然流畅的中文表达，不要逐词硬翻；\n"
        "2. 型号/尺寸/数字/单位/商标（如 ABS、PP、USB-C、oz、lb）保持原样；\n"
        "3. 不要添加解释、不要改写结构、不要输出原文；\n"
        "4. 严格输出 JSON 数组，长度和顺序与输入完全一致，形如 [\"译文0\",\"译文1\"]，不要附加任何其它字段或说明。"
    )
    user_prompt = f"请把以下 {len(texts)} 条文本翻译为{lang_name}，按相同顺序返回 JSON 数组：\n{numbered}"

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        raw = model_pool.call_llm(
            messages,
            temperature=0.1,
            max_tokens=4096,
            timeout=120,
            _log_module="lAi_listing_translate",
            preferred_model=translate_preferred,
        )
    except Exception as e:
        logger.exception("翻译调用失败")
        raise HTTPException(status_code=502, detail=f"翻译失败: {e}")

    translations: list[str] = []
    if raw:
        text = raw.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
            text = text.strip()
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                parsed = json.loads(text[start:end + 1])
                if isinstance(parsed, list):
                    translations = [str(x) if x is not None else "" for x in parsed]
            except Exception:
                logger.warning("翻译 JSON 解析失败，将返回逐行 fallback。raw=%s", text[:200])

    if len(translations) != len(texts):
        if len(translations) < len(texts):
            translations = translations + [""] * (len(texts) - len(translations))
        else:
            translations = translations[: len(texts)]

    return TranslateResponse(
        translations=translations,
        target_lang=target,
        model=translate_preferred,
    )
