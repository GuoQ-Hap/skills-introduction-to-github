from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from enum import Enum

from pydantic import BaseModel, Field


class OptimizeStrategy(str, Enum):
    """优化策略枚举"""
    STANDARD = "standard"   # 经典 SEO 优化
    COSMO = "cosmo"         # COSMO 四维算法策略
    CTR = "ctr"             # 侧重 CTR 点击率优化
    CVR = "cvr"             # 侧重 CVR 转化率优化
    TRAFFIC = "traffic"     # 侧重流量/关键词覆盖优化
    CUSTOM = "custom"       # 完全自定义参数优化


class ReviewItem(BaseModel):
    """单条用户评论（来自产品页 Top Reviews）"""
    stars: float = Field(0, description="星级 1~5")
    title: str = Field("", description="评论标题")
    body: str = Field("", description="评论正文")
    date: str = Field("", description="评论日期原文")


class ProductData(BaseModel):
    asin: str
    marketplace: str = ""
    title: str = ""
    brand: str = ""
    price: str = ""
    currency: str = ""
    rating: str = ""
    review_count: str = ""
    bullet_points: List[str] = []
    description: str = ""
    category: str = ""
    bsr_rank: str = ""
    images: List[str] = []
    reviews: List[ReviewItem] = Field(default_factory=list, description="Top Reviews（最多10条）")
    variants: List[Dict[str, Any]] = []
    raw_html_snippet: str = Field("", exclude=True)


class TriDimDiagnostic(BaseModel):
    """三维诊断指标（来自 Doris 广告数据）"""
    product_ctr_pct: Optional[float] = Field(None, description="产品 CTR%")
    cat_avg_ctr_pct: Optional[float] = Field(None, description="类目平均 CTR%")
    product_cvr_pct: Optional[float] = Field(None, description="产品 CVR%")
    cat_avg_cvr_pct: Optional[float] = Field(None, description="类目平均 CVR%")
    sessions_change_pct: Optional[float] = Field(None, description="流量变化%")
    avg_stock_qty: Optional[int] = Field(None, description="平均库存")
    hit_count: int = Field(0, description="命中维度数")
    optimization_actions: str = Field("", description="优化建议")
    msku: str = Field("", description="MSKU")
    store_name: str = Field("", description="店铺名")
    country_code: str = Field("", description="国家代码")
    category_2: str = Field("", description="二级类目")
    total_volume: Optional[int] = Field(None, description="总销量")
    total_amount: Optional[float] = Field(None, description="总销售额")


class TrafficWordItem(BaseModel):
    """流量词条目（用于前端列举供用户框选）"""
    word: str = Field("", description="流量词")
    aba_search_rank: Optional[int] = Field(None, description="ABA 搜索排名")
    sqr_total_impressions: Optional[int] = Field(None, description="SQR search_query_count 汇总（接口字段名沿用）")
    source: str = Field("", description="来源: aba/sqr/both")
    relevance: str = Field("unknown", description="描述准确性: clear/fuzzy/broad/unknown")
    reason: str = Field("", description="判定理由")


class FetchDiagnosticsResponse(BaseModel):
    """获取产品信息 + 三维诊断 + 流量词 + 评论分析的统一响应"""
    product: ProductData
    tri_dim: Optional[TriDimDiagnostic] = Field(None, description="三维诊断指标")
    traffic_words: List[TrafficWordItem] = Field(default_factory=list, description="流量词列表")
    traffic_word_count: int = Field(0, description="流量词总数")
    review_analysis: Optional["ReviewAnalysisResult"] = Field(
        None, description="评论分析结果（卖点/痛点/核心特点）",
    )
    db_color: str = Field(
        "",
        description="产品颜色（来自 leang_product_info.colour，英文）；供竞品发现/优化阶段带入",
    )
    error: Optional[str] = None


class TriDimDiagnosticSqlRequest(BaseModel):
    """生成三维诊断 Doris SQL（与 triDimSqlService 一致，供前端 execSql 与后端自查共用）。"""
    date_range: int = Field(30, ge=1, le=366)
    asin: Optional[str] = Field(None, description="可选，筛选 ASIN")
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=500)
    dims: Optional[List[str]] = Field(
        None, description="ctr / cvr / sessions；不传表示三维度全开"
    )
    thresholds: Optional[Dict[str, Any]] = Field(
        None,
        description="diag_ctr_abs、diag_cvr_abs、diag_sess_dec（百分比数值，与前端 ThresholdConfig 一致）",
    )
    row_filter: bool = Field(
        True,
        description="为 True 时仅保留至少命中一维异常的记录（与数据分析页一致）；抓取摘要 tri_dim 用 False",
    )
    include_count_sql: bool = Field(False, description="是否同时返回 count_sql")


class TriDimDiagnosticSqlResponse(BaseModel):
    data_sql: str
    count_sql: Optional[str] = None


class FetchProductRequest(BaseModel):
    asin: str = Field(..., min_length=10, max_length=10, description="亚马逊 ASIN（10位）")
    marketplace: str = Field("US", description="站点代码: US/UK/DE/JP/CA 等")


class CustomOptimizeParams(BaseModel):
    """自定义优化模式的扩展参数"""
    custom_instructions: str = Field("", description="用户自定义优化指令（核心优化目标和要求）")
    tone: str = Field("professional", description="文案风格: professional/friendly/luxury/budget/technical")
    focus_point: str = Field("", description="重点优化方向（如：突出环保材质、强调性价比等）")
    extra_context: str = Field("", description="额外的产品背景信息或市场情报")
    title_strategy: str = Field("", description="标题优化策略（如：品牌优先、关键词优先等）")
    bullet_style: str = Field("", description="五点描述风格（如：场景驱动、功能驱动、情感驱动）")


class ListingOptimizeRequest(BaseModel):
    asin: str = Field(..., min_length=10, max_length=10, description="亚马逊 ASIN（10位）")
    marketplace: str = Field("US", description="站点代码: US/UK/DE/JP/CA 等")
    target_keywords: List[str] = Field(default_factory=list, description="希望重点覆盖的关键词")
    target_audience: str = Field("", description="修改意见 / 补充说明")
    language: str = Field("", description="输出语言，留空则根据站点自动选择")
    optimize_strategy: OptimizeStrategy = Field(
        OptimizeStrategy.STANDARD,
        description="优化策略: standard/cosmo/ctr/cvr/traffic/custom",
    )
    session_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    model: Optional[str] = Field(None, description="指定模型 provider:model，空则使用主模型")
    eval_model: Optional[str] = Field(
        None,
        description="多候选评分阶段使用的模型 provider:model；空则回退到 model",
    )
    prompt_overrides: Optional[Dict[str, str]] = Field(
        None,
        description="提示词可配置部分覆盖",
    )
    product_data: Optional[ProductData] = Field(None, description="已编辑的产品数据，传入则跳过抓取")
    optimize_sections: Optional[List[str]] = Field(
        None,
        description="选择性优化: title / bullet_points / description / search_terms，不传则全部优化",
    )
    competitor_products: Optional[List[ProductData]] = Field(
        None,
        description="竞品产品数据列表，作为优化参考",
    )
    custom_params: Optional[CustomOptimizeParams] = Field(
        None,
        description="自定义优化模式扩展参数（strategy=custom 时使用）",
    )
    enable_fab: bool = Field(
        True,
        description="是否启用 FAB 增强模式（COSMO + FAB + 评论洞察 + 备选方案）",
    )
    review_analysis: Optional["ReviewAnalysisResult"] = Field(
        None,
        description="评论分析结果（来自产品获取阶段，用于增强优化提示词）",
    )
    variant_count: int = Field(
        1, ge=1, le=10,
        description="候选文案数量（1~10）。>1 时并行生成多个候选并用 LLM 四维评分择优",
    )
    color: str = Field(
        "",
        description="产品颜色（如 Pink / Black），来源 leang_product_info.colour；为空则后端自动查询。"
                    "用于在优化 prompt 中提示 LLM 保留并正确表达该颜色属性。",
    )
    tri_dim: Optional["TriDimDiagnostic"] = Field(
        None,
        description="三维诊断指标（来自抓取阶段）；用于按命中情况对曝光/转化评分进行加权。"
                    "为空时后端会尝试自动从 Doris 查询一次作为兜底。",
    )


class TrafficWordDetail(BaseModel):
    """单个流量词的详细信息"""
    word: str = Field("", description="词语")
    aba_search_rank: Optional[int] = Field(None, description="ABA 最佳搜索排名")
    aba_record_count: int = Field(0, description="ABA 命中记录数")
    sqr_total_impressions: Optional[int] = Field(None, description="SQR search_query_count 汇总（接口字段名沿用）")
    sqr_record_count: int = Field(0, description="SQR 命中记录数")
    relevance: str = Field("unknown", description="描述准确性: clear/fuzzy/broad/unknown")
    keep: Optional[bool] = Field(None, description="是否保留（clear=True, fuzzy/broad=None 由用户决定）")
    alternatives: List[str] = Field(default_factory=list, description="替代词建议")
    reason: str = Field("", description="相关性判定理由")


class WordAnalysis(BaseModel):
    """优化结果的词语分析"""
    traffic_words: List[TrafficWordDetail] = Field(default_factory=list, description="流量词列表")
    keyword_words: List[str] = Field(default_factory=list, description="用户指定的目标关键词")
    description_words: List[str] = Field(default_factory=list, description="描述性词语")
    total_checked: int = Field(0, description="总共检查的词数")


class OptimizedListing(BaseModel):
    title: str = Field("", description="优化后的标题")
    bullet_points: List[str] = Field(default_factory=list, description="优化后的五点描述")
    description: str = Field("", description="优化后的产品描述")
    search_terms: str = Field("", description="后台搜索关键词")
    optimization_notes: str = Field("", description="优化说明与建议")
    word_analysis: Optional[WordAnalysis] = Field(None, description="词语分析（流量词/关键词/描述词）")


class FreeFormScore(BaseModel):
    """转化评分（LLM 仅从 CTR/CVR / 转化能力单一视角给出 0-100 分）。

    与 COSMO/关键词/Rufus/IDQ 四维评分（曝光评分）并列，两套评分按三维诊断命中
    结果加权组成候选总分。字段名保留 free_form_score 是出于向后兼容，当前语义
    等同于"转化评分"。
    """
    total: int = Field(0, ge=0, le=100, description="LLM 对 Listing 转化力给出的总分")
    summary: str = Field("", description="一句话转化力评价")
    strengths: List[str] = Field(default_factory=list, description="促进转化的亮点")
    weaknesses: List[str] = Field(default_factory=list, description="影响转化的短板")
    suggestions: List[str] = Field(default_factory=list, description="拉高转化的改进建议")


class OptimizedVariant(BaseModel):
    """多候选优化产出的单个文案（含评分）。

    两套评分并列：
    - scores / total_score：曝光评分（COSMO/关键词/Rufus/IDQ 四维规则打分）
    - free_form_score：转化评分（LLM 直接从转化角度打分，字段名保留为 free_form_score 以兼容）
    最优候选由 composite_score 决定，权重按三维诊断命中情况动态分配。
    """
    variant_index: int = Field(0, description="候选序号（从 0 起）")
    listing: OptimizedListing = Field(default_factory=OptimizedListing, description="候选文案")
    scores: Optional["EvaluateScores"] = Field(None, description="曝光评分（四维规则打分）的细分")
    total_score: int = Field(0, description="曝光评分总分 0-100")
    overall_summary: str = Field("", description="曝光评分综合评语")
    priority_actions: List[str] = Field(default_factory=list, description="优先改进建议（来自曝光评分）")
    is_best: bool = Field(False, description="是否为最优候选（由 composite_score 决定）")
    generate_error: Optional[str] = Field(None, description="生成阶段错误信息（若有）")
    evaluate_error: Optional[str] = Field(None, description="曝光评分阶段错误信息（若有）")
    free_form_score: Optional[FreeFormScore] = Field(
        None,
        description="转化评分：LLM 仅从转化角度给出 0-100 分，与曝光评分加权得到 composite_score。",
    )
    free_form_error: Optional[str] = Field(
        None, description="转化评分阶段错误信息（若有）",
    )
    composite_score: float = Field(
        0.0,
        description="加权复合总分 = 曝光分×w_expose + 转化分×w_conversion，用于最优候选排序。",
    )


class TriDimHitSummary(BaseModel):
    """三维诊断命中摘要（用于候选加权排序的决策依据）。"""
    sessions_decline: bool = Field(False, description="是否命中『流量下降』")
    ctr_low: bool = Field(False, description="是否命中『CTR 低』")
    cvr_low: bool = Field(False, description="是否命中『CVR 低』")
    conversion_hit: bool = Field(False, description="转化类是否命中（ctr_low 或 cvr_low）")
    weight_expose: float = Field(0.5, description="曝光评分权重")
    weight_conversion: float = Field(0.5, description="转化评分权重")
    rule: str = Field("", description="命中到权重的规则说明")


class ListingOptimizeResponse(BaseModel):
    asin: str
    marketplace: str
    original: ProductData
    optimized: OptimizedListing
    variants: List[OptimizedVariant] = Field(
        default_factory=list,
        description="多候选文案列表（仅 variant_count>1 时有值），已按 composite_score 倒序排列",
    )
    best_variant_index: Optional[int] = Field(
        None, description="最优候选在 variants 中的索引（variant_count>1 时有值）",
    )
    tri_dim_hit: Optional[TriDimHitSummary] = Field(
        None,
        description="三维诊断命中摘要与采用的曝光/转化加权（variant_count>1 时有值）",
    )
    error: Optional[str] = None


class ListingAnalyzeRequest(BaseModel):
    asin: str = Field(..., min_length=10, max_length=10)
    marketplace: str = Field("US")
    search_terms: str = Field("", description="后台搜索关键词（可选，用于评估关键词互补性）")
    session_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    model: Optional[str] = Field(None, description="指定模型 provider:model，空则使用主模型")
    product_data: Optional[ProductData] = Field(None, description="已编辑的产品数据，传入则跳过抓取")


class ListingAnalyzeResponse(BaseModel):
    asin: str
    marketplace: str
    product: ProductData
    analysis: str = Field("", description="兼容旧版：文本摘要（从四维评判结果生成）")
    score: Optional[int] = Field(None, description="总分（满分 100）")
    scores: Optional[EvaluateScores] = Field(None, description="四维分项评分")
    evaluate_analysis: Optional[EvaluateAnalysis] = Field(None, description="四维分析详情")
    overall_summary: str = ""
    priority_actions: List[str] = Field(default_factory=list)
    error: Optional[str] = None


# ── 四维算法评判（COSMO / 关键词 / Rufus / IDQ） ──


class ListingEvaluateRequest(BaseModel):
    asin: str = Field(..., min_length=10, max_length=10)
    marketplace: str = Field("US")
    search_terms: str = Field("", description="后台搜索关键词（可选，用于评估关键词互补性）")
    session_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    model: Optional[str] = Field(None, description="指定模型 provider:model，空则使用主模型")
    product_data: Optional[ProductData] = Field(None, description="已编辑的产品数据，传入则跳过抓取")


class DimensionScore(BaseModel):
    """单维度分项得分"""
    subtotal: int = Field(0, ge=0, le=25, description="维度小计（满分 25）")


class CosmoScore(DimensionScore):
    entity_relations: int = Field(0, ge=0, le=5)
    intent_mapping: int = Field(0, ge=0, le=5)
    scene_coverage: int = Field(0, ge=0, le=5)
    decision_path: int = Field(0, ge=0, le=5)
    attribute_need_link: int = Field(0, ge=0, le=5)


class KeywordsScore(DimensionScore):
    core_keywords: int = Field(0, ge=0, le=5)
    longtail_distribution: int = Field(0, ge=0, le=5)
    position_weight: int = Field(0, ge=0, le=5)
    synonyms_variants: int = Field(0, ge=0, le=5)
    density_naturalness: int = Field(0, ge=0, le=5)


class RufusScore(DimensionScore):
    core_info_qa: int = Field(0, ge=0, le=5)
    spec_structure: int = Field(0, ge=0, le=5)
    usage_guide: int = Field(0, ge=0, le=5)
    competitive_diff: int = Field(0, ge=0, le=5)
    faq_coverage: int = Field(0, ge=0, le=5)


class IdqScore(DimensionScore):
    required_attrs: int = Field(0, ge=0, le=5)
    content_richness: int = Field(0, ge=0, le=5)
    category_attrs: int = Field(0, ge=0, le=5)
    compliance: int = Field(0, ge=0, le=5)
    synergy: int = Field(0, ge=0, le=5)


class EvaluateScores(BaseModel):
    cosmo: CosmoScore = Field(default_factory=CosmoScore)
    keywords: KeywordsScore = Field(default_factory=KeywordsScore)
    rufus: RufusScore = Field(default_factory=RufusScore)
    idq: IdqScore = Field(default_factory=IdqScore)
    total: int = Field(0, ge=0, le=100)


class DimensionAnalysis(BaseModel):
    summary: str = ""
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)


class KeywordsAnalysis(DimensionAnalysis):
    identified_core_keywords: List[str] = Field(default_factory=list)
    missing_keywords: List[str] = Field(default_factory=list)


class RufusAnalysis(DimensionAnalysis):
    answerable_questions: List[str] = Field(default_factory=list)
    unanswerable_questions: List[str] = Field(default_factory=list)


class ContentStats(BaseModel):
    title_chars: int = 0
    bullet_count: int = 0
    avg_bullet_chars: int = 0
    description_chars: int = 0
    search_terms_bytes: int = 0


class IdqAnalysis(DimensionAnalysis):
    content_stats: ContentStats = Field(default_factory=ContentStats)
    compliance_issues: List[str] = Field(default_factory=list)


class EvaluateAnalysis(BaseModel):
    cosmo: DimensionAnalysis = Field(default_factory=DimensionAnalysis)
    keywords: KeywordsAnalysis = Field(default_factory=KeywordsAnalysis)
    rufus: RufusAnalysis = Field(default_factory=RufusAnalysis)
    idq: IdqAnalysis = Field(default_factory=IdqAnalysis)


class ListingEvaluateResponse(BaseModel):
    asin: str
    marketplace: str
    product: ProductData
    scores: EvaluateScores = Field(default_factory=EvaluateScores)
    analysis: EvaluateAnalysis = Field(default_factory=EvaluateAnalysis)
    overall_summary: str = ""
    priority_actions: List[str] = Field(default_factory=list)
    raw_output: str = Field("", description="LLM 原始输出（JSON 解析失败时回退）")
    error: Optional[str] = None


class ListingRefineRequest(BaseModel):
    asin: str = Field(..., min_length=10, max_length=10)
    marketplace: str = Field("US")
    current_title: str = Field("")
    current_bullet_points: List[str] = Field(default_factory=list)
    current_description: str = Field("")
    current_search_terms: str = Field("")
    user_feedback: str = Field(..., min_length=1, description="用户修改意见")
    session_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    model: Optional[str] = Field(None)


class ListingRefineResponse(BaseModel):
    asin: str
    marketplace: str
    optimized: OptimizedListing
    error: Optional[str] = None


class ListingEmbedRequest(BaseModel):
    asin: str = Field(..., min_length=10, max_length=10)
    marketplace: str = Field("US")
    title: str = Field("", description="标题")
    bullet_points: List[str] = Field(default_factory=list, description="五点描述")
    description: str = Field("", description="产品描述")
    search_terms: str = Field("", description="后台搜索关键词")


class ListingEmbedResponse(BaseModel):
    success: bool
    message: str = ""
    collection: str = ""
    insert_count: int = 0


class LingxingSubmitRequest(BaseModel):
    asin: str = Field(..., min_length=10, max_length=10, description="目标 ASIN")
    marketplace: str = Field("US", description="站点代码")
    title: str = Field("", description="优化后标题")
    bullet_points: List[str] = Field(default_factory=list, description="优化后五点描述")
    description: str = Field("", description="优化后产品描述")
    search_terms: str = Field("", description="优化后搜索关键词")


class LingxingSubmitResponse(BaseModel):
    success: bool
    message: str = ""
    detail: Optional[Dict[str, Any]] = None


class TrafficWordCheckRequest(BaseModel):
    """流量词检查请求"""
    words: List[str] = Field(default_factory=list, description="要检查的词语列表")
    title: str = Field("", description="优化后标题（用于提取词语）")
    bullet_points: List[str] = Field(default_factory=list, description="优化后五点描述")
    description: str = Field("", description="优化后描述")
    search_terms: str = Field("", description="后台搜索词")
    target_keywords: List[str] = Field(default_factory=list, description="用户指定的目标关键词")
    product_title: str = Field("", description="原始产品标题（用于相关性判定）")
    product_category: str = Field("", description="产品类目（用于相关性判定）")


class TrafficWordCheckResponse(BaseModel):
    """流量词检查响应"""
    word_analysis: WordAnalysis
    error: Optional[str] = None


class TrafficWordDecisionRequest(BaseModel):
    """用户对弱相关流量词的保留/替换决定"""
    asin: str = Field(..., min_length=10, max_length=10)
    marketplace: str = Field("US")
    decisions: Dict[str, bool] = Field(
        ..., description="流量词 → 是否保留 的映射",
    )
    replacements: Dict[str, str] = Field(
        default_factory=dict,
        description="流量词 → 替换词 的映射（不保留时使用）",
    )
    current_title: str = Field("")
    current_bullet_points: List[str] = Field(default_factory=list)
    current_description: str = Field("")
    current_search_terms: str = Field("")
    session_id: str = Field(default_factory=lambda: __import__("uuid").uuid4().hex)
    model: Optional[str] = None


class LAIHealthResponse(BaseModel):
    status: str
    time: str
    model: str


# ── 后台任务 ──────────────────────────────


class CompetitorDiscoveryRequest(BaseModel):
    """竞品发现请求（通过 Amazon 搜索）"""
    asin: str = Field(..., min_length=10, max_length=10)
    marketplace: str = Field("US")
    price_tolerance: float = Field(0.3, ge=0.05, le=1.0, description="价格浮动比例，默认 ±30%")
    max_results: int = Field(20, ge=1, le=100)
    with_details: bool = Field(
        False,
        description="是否并发抓取每条竞品的完整 ProductData（bullet/description），用于竞品差异化描述。",
    )
    color: str = Field(
        "",
        description="搜索关键词附加的颜色（如 Pink / Black）；为空则后端自动从 leang_product_info.colour 查询",
    )


class CompetitorItem(BaseModel):
    """单条竞品（来自 Amazon 搜索结果）"""
    asin: str = ""
    title: str = ""
    price: str = ""
    currency: str = ""
    rating: str = ""
    review_count: str = ""
    image: str = ""
    avg_price: Optional[float] = Field(None, description="提取的数值价格")
    # ── 维度抽取（从 title / proxy 字段解析，供前端按勾选筛选） ──
    color: str = Field("", description="主色调（从标题抽取的颜色词，小写英文）")
    size: str = Field("", description="尺寸（从标题抽取，如 S/M/L/XL/12inch 等）")
    style: str = Field("", description="款式/花色（如 solid/stripe/floral/modern 等）")
    # ── 可选详情（with_details=True 时填充，供大模型做差异化对比） ──
    product_data: Optional[ProductData] = Field(
        None, description="完整产品数据，包含 bullet_points / description，用于竞品差异化分析",
    )


class CompetitorDiscoveryResponse(BaseModel):
    """竞品发现响应"""
    source_asin: str = ""
    source_category_2: str = ""
    source_avg_price: Optional[float] = None
    source_total_volume: Optional[Any] = None
    competitors: List[CompetitorItem] = Field(default_factory=list)
    total_found: int = 0
    # ── 维度聚合（供前端勾选筛选；顺序按出现频次倒序） ──
    available_colors: List[str] = Field(default_factory=list, description="竞品集合中出现的颜色词")
    available_sizes: List[str] = Field(default_factory=list, description="竞品集合中出现的尺寸词")
    available_styles: List[str] = Field(default_factory=list, description="竞品集合中出现的款式/花色词")
    error: Optional[str] = None


class TaskSubmitRequest(BaseModel):
    """提交后台任务请求"""
    action: str = Field(
        ...,
        description="任务类型: optimize / analyze / discover_competitors / review_analysis / fetch_product / fetch_reviews",
    )
    optimize_params: Optional[ListingOptimizeRequest] = Field(
        None, description="当 action=optimize 时的参数",
    )
    analyze_params: Optional[ListingAnalyzeRequest] = Field(
        None, description="当 action=analyze 时的参数",
    )
    competitor_params: Optional[CompetitorDiscoveryRequest] = Field(
        None, description="当 action=discover_competitors 时的参数",
    )
    review_analysis_params: Optional["ReviewAnalysisRequest"] = Field(
        None, description="当 action=review_analysis 时的参数",
    )
    fetch_params: Optional[FetchProductRequest] = Field(
        None, description="当 action=fetch_product 或 fetch_reviews 时的参数",
    )


class TaskSubmitResponse(BaseModel):
    task_id: str


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str = Field(..., description="pending / running / completed / failed")
    action: str
    result: Optional[Dict[str, Any]] = None
    partial_result: Optional[Dict[str, Any]] = Field(
        None,
        description="运行中的阶段性产出（如多候选生成/评分进度），供前端实时渲染",
    )
    error: Optional[str] = None
    elapsed_ms: Optional[int] = None
    created_at: str = ""
    asin: str = ""
    marketplace: str = ""


class TaskListResponse(BaseModel):
    tasks: List[TaskStatusResponse] = Field(default_factory=list)


# ── 搜索词相关性推荐 ────────────────────────


class SearchTermRecommendRequest(BaseModel):
    """搜索词相关性推荐请求"""
    asin: str = Field(..., min_length=10, max_length=10, description="Amazon ASIN")
    relevance_filter: Optional[str] = Field(
        None,
        description="单一相关性等级，如 '高相关'；为 None 返回全部非'不相关'",
    )


class SearchTermRecommendItem(BaseModel):
    """单条搜索词相关性结果"""
    search_term: str
    relevance: str = ""
    total_score: Optional[float] = None
    size_score: Optional[float] = None
    color_score: Optional[float] = None
    pattern_score: Optional[float] = None
    style_score: Optional[float] = None


class SearchTermRecommendResponse(BaseModel):
    """搜索词相关性推荐响应"""
    success: bool
    message: str = ""
    msku_info: List[Dict[str, Any]] = Field(default_factory=list)
    matched_msku: Optional[str] = None
    matched_store: Optional[str] = None
    matched_dir_store: Optional[str] = None
    matched_file: Optional[str] = None
    summary: Dict[str, int] = Field(
        default_factory=dict,
        description="各相关性等级的搜索词数量统计",
    )
    total_unique: int = Field(0, description="去重后搜索词总数")
    returned_count: int = Field(0, description="本次返回条数")
    search_terms: List[SearchTermRecommendItem] = Field(default_factory=list)


class SqrSearchVolumeRequest(BaseModel):
    """按需查询单个搜索词在 SQR 报表中的搜索量汇总（悬停用，勿批量滥用）。"""
    term: str = Field(..., min_length=1, max_length=500, description="搜索词原文")


class SqrSearchVolumeResponse(BaseModel):
    term: str = ""
    total_search_count: int = Field(0, description="SQR search_query_count 在时间窗内汇总")
    grade: str = Field("", description="搜索量档位 A~F")
    grade_label: str = Field("", description="档位中文说明")
    since_date: str = Field("", description="统计起始日期（含）")
    cached: bool = Field(False, description="是否命中服务端进程缓存")


class SqrSearchVolumesRequest(BaseModel):
    """一次 SQL 聚合多词 SQR 搜索量（列表筛选用，每请求最多 500 词）。"""
    terms: List[str] = Field(default_factory=list, description="搜索词列表")


class SqrSearchVolumesResponse(BaseModel):
    """key 为小写搜索词，value 为单条 SQR 汇总结果。"""
    volumes: Dict[str, SqrSearchVolumeResponse] = Field(default_factory=dict)


# ═══════════════════════════════════════════════
# 评论分析
# ═══════════════════════════════════════════════

class ReviewAnalysisRequest(BaseModel):
    """评论分析请求。reviews 可来自抓取、也可手动上传。"""
    asin: str = Field("", description="ASIN（可选，来自抓取时携带）")
    marketplace: str = Field("", description="站点")
    product_title: str = Field("", description="产品标题（可选，为 LLM 提供上下文）")
    reviews: List[ReviewItem] = Field(default_factory=list, description="评论列表")
    model: str = Field("", description="指定 LLM 模型（可选）")


class PainPoint(BaseModel):
    """用户痛点"""
    title: str = Field("", description="痛点简述")
    detail: str = Field("", description="具体描述")
    frequency: str = Field("low", description="出现频率: high/medium/low")
    related_reviews: List[int] = Field(default_factory=list, description="关联评论索引")


class SellingPoint(BaseModel):
    """产品卖点"""
    title: str = Field("", description="卖点简述")
    detail: str = Field("", description="具体描述")
    frequency: str = Field("low", description="出现频率: high/medium/low")
    related_reviews: List[int] = Field(default_factory=list, description="关联评论索引")


class CoreFeature(BaseModel):
    """产品核心特点"""
    title: str = Field("", description="特点简述")
    detail: str = Field("", description="具体描述")
    sentiment: str = Field("neutral", description="整体情感: positive/neutral/negative")


class ReviewAnalysisResult(BaseModel):
    """评论分析结果"""
    pain_points: List[PainPoint] = Field(default_factory=list, description="用户主要痛点")
    selling_points: List[SellingPoint] = Field(default_factory=list, description="产品主要卖点")
    core_features: List[CoreFeature] = Field(default_factory=list, description="产品核心特点")
    overall_sentiment: str = Field("", description="整体情感倾向")
    summary: str = Field("", description="综合分析摘要")


class ReviewAnalysisResponse(BaseModel):
    """评论分析响应"""
    asin: str = ""
    marketplace: str = ""
    review_count: int = 0
    analysis: Optional[ReviewAnalysisResult] = None
    error: Optional[str] = None


# NOTE: BulletRegenerateRequest / BulletRegenerateResponse 已随"3 条备选"功能下线移除。


class TranslateRequest(BaseModel):
    """批量翻译请求（用于前端 hover 时查看中文翻译）"""
    texts: List[str] = Field(default_factory=list, description="需要翻译的文本列表，按索引保持顺序")
    target_lang: str = Field("zh-CN", description="目标语言，默认简体中文")
    source_lang: Optional[str] = Field(None, description="源语言提示，可为空让模型自行识别")
    preferred_model: Optional[str] = Field(
        None,
        description="已忽略；翻译接口固定使用模型池中的 gpt-4o-mini",
    )


class TranslateResponse(BaseModel):
    """批量翻译响应"""
    translations: List[str] = Field(default_factory=list, description="与 texts 一一对应的翻译结果")
    target_lang: str = "zh-CN"
    model: str = ""
