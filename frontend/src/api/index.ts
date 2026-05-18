import axios from 'axios';

/** 全局版本号，与后端 version.py 保持同步 */
export const APP_VERSION = 'v0.1';
export const APP_STAGE = '测试版';
export const APP_VERSION_FULL = `${APP_VERSION} ${APP_STAGE}`;

const TOKEN_KEY = 'leang_auth_token';

const api = axios.create({
  baseURL: '',
  timeout: 300000,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    config.headers.set('Authorization', `Bearer ${token}`);
  }
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem('leang_user_info');
      window.dispatchEvent(new Event('auth:expired'));
    }
    const msg = err.response?.data?.detail || err.message || '请求失败';
    const wrapped = new Error(msg) as Error & { status?: number };
    wrapped.status = err.response?.status;
    return Promise.reject(wrapped);
  },
);

/** 获取当前登录用户名（从 localStorage 用户信息） */
export function getCurrentUsername(): string {
  try {
    const raw = localStorage.getItem('leang_user_info');
    if (raw) return JSON.parse(raw)?.username || 'guest';
  } catch { /* */ }
  return 'guest';
}

/** 获取用户域 key，防止不同用户数据混用 */
export function getUserScopedKey(key: string): string {
  const username = getCurrentUsername();
  return username !== 'guest' ? `${key}_${username}` : key;
}

export interface ReviewItem {
  stars: number;
  title: string;
  body: string;
  date: string;
}

export interface ProductData {
  asin: string;
  marketplace: string;
  title: string;
  brand: string;
  price: string;
  currency: string;
  rating: string;
  review_count: string;
  bullet_points: string[];
  description: string;
  category: string;
  bsr_rank: string;
  monthly_sales_text?: string;
  images: string[];
  reviews: ReviewItem[];
}

export interface TriDimDiagnostic {
  product_ctr_pct: number | null;
  cat_avg_ctr_pct: number | null;
  product_cvr_pct: number | null;
  cat_avg_cvr_pct: number | null;
  sessions_change_pct: number | null;
  avg_stock_qty: number | null;
  hit_count: number;
  optimization_actions: string;
  msku: string;
  store_name: string;
  country_code: string;
  category_2: string;
  total_volume: number | null;
  total_amount: number | null;
}

export interface TrafficWordItem {
  word: string;
  aba_search_rank: number | null;
  /** SQR 表 search_query_count 汇总（字段名历史原因仍为 impressions） */
  sqr_total_impressions: number | null;
  source: string;
  /** 描述准确性: clear / fuzzy / broad / unknown */
  relevance?: string;
  /** 相关性判定理由 */
  reason?: string;
}

export interface SpAdInsightItem {
  date_start: string;
  date_end: string;
  store_name: string;
  country_code: string;
  profile_id: string;
  asin: string;
  sku: string;
  word_type: string;
  word_text: string;
  match_type: string;
  campaign_id: string;
  campaign_name: string;
  ad_group_id: string;
  ad_group_name: string;
  impressions: number;
  clicks: number;
  cost: number;
  orders: number;
  sales: number;
  units: number;
  ctr: number;
  cpc: number;
  cvr: number;
  acos: number;
  roas: number;
  insight_type: string;
  source_table: string;
  reason: string;
}

export interface SpAdInsightResponse {
  asin: string;
  store_name: string;
  days: number;
  table: string;
  total: number;
  summary: Record<string, number>;
  items: SpAdInsightItem[];
  error?: string;
}

export interface FetchDiagnosticsResponse {
  product: ProductData;
  tri_dim: TriDimDiagnostic | null;
  traffic_words: TrafficWordItem[];
  traffic_word_count: number;
  sp_ad_insights: SpAdInsightItem[];
  sp_ad_insight_count: number;
  review_analysis?: ReviewAnalysisResult | null;
  /** 来自 leang_product_info.colour 的产品颜色（英文），供竞品发现 / 优化阶段带入 */
  db_color?: string;
  error?: string;
}

/** POST /lsta/tri-dim-diagnostic-sql — 与后端 triDimSqlService 同源 */
export interface TriDimDiagnosticSqlRequest {
  date_range: number;
  asin?: string;
  page?: number;
  page_size?: number;
  dims?: string[];
  thresholds?: { diag_ctr_abs?: number; diag_cvr_abs?: number; diag_sess_dec?: number };
  row_filter?: boolean;
  include_count_sql?: boolean;
  sales_apartment?: string;
}

export interface TriDimDiagnosticSqlResponse {
  data_sql: string;
  count_sql?: string | null;
}

export interface TrafficWordDetail {
  word: string;
  aba_search_rank?: number | null;
  aba_record_count: number;
  sqr_total_impressions?: number | null;
  sqr_record_count: number;
  relevance: 'clear' | 'fuzzy' | 'broad' | 'unknown';
  keep?: boolean | null;
  alternatives: string[];
  reason: string;
}

export interface WordAnalysis {
  traffic_words: TrafficWordDetail[];
  keyword_words: string[];
  description_words: string[];
  total_checked: number;
}

export interface OptimizedListing {
  title: string;
  bullet_points: string[];
  description: string;
  search_terms: string;
  optimization_notes: string;
  word_analysis?: WordAnalysis | null;
}

/** 转化评分：LLM 仅从转化视角对整段 Listing 给出的 0-100 分。
 *  字段名 free_form_score 保留以兼容前后端，语义等同"转化评分"。 */
export interface FreeFormScore {
  total: number;
  summary: string;
  strengths: string[];
  weaknesses: string[];
  suggestions: string[];
}

export interface OptimizedVariant {
  variant_index: number;
  listing: OptimizedListing;
  /** 曝光评分（COSMO/关键词/Rufus/IDQ 四维规则打分）细分 */
  scores?: EvaluateScores | null;
  /** 曝光评分总分 0-100 */
  total_score: number;
  /** 曝光评分综合评语 */
  overall_summary: string;
  priority_actions: string[];
  is_best: boolean;
  generate_error?: string | null;
  evaluate_error?: string | null;
  /** 转化评分（与曝光评分并列） */
  free_form_score?: FreeFormScore | null;
  free_form_error?: string | null;
  /** 加权复合总分 = 曝光×w_expose + 转化×w_conversion */
  composite_score?: number;
}

/** 三维诊断命中摘要 + 实际采用的曝光/转化加权 */
export interface TriDimHitSummary {
  sessions_decline: boolean;
  ctr_low: boolean;
  cvr_low: boolean;
  conversion_hit: boolean;
  weight_expose: number;
  weight_conversion: number;
  rule: string;
}

export interface ListingOptimizeResponse {
  asin: string;
  marketplace: string;
  original: ProductData;
  optimized: OptimizedListing;
  /** 多候选产出（variant_count>1 时有值），已按 composite_score 倒序排列 */
  variants?: OptimizedVariant[];
  /** 最优候选在 variants 中的索引（variant_count>1 时有值） */
  best_variant_index?: number | null;
  /** 三维诊断命中摘要 + 实际采用的加权 */
  tri_dim_hit?: TriDimHitSummary | null;
  /** 本次优化在 llm_memory 表的主键，用于回收用户反馈 */
  memory_id?: number | null;
  /** 多候选模式下每条 variant 各自的 llm_memory.id，顺序与 variants 一一对应 */
  variant_memory_ids?: (number | null)[];
  error?: string;
}

export interface ListingOptimizeMetricSnapshot {
  metric_start: string;
  metric_end: string;
  period_days: number;
  ctr?: number | null;
  cvr?: number | null;
  traffic?: number | null;
  sessions_change_pct?: number | null;
  store_name?: string;
  country_code?: string;
  msku?: string;
  category_2?: string;
  total_volume?: number | null;
  total_amount?: number | null;
}

export interface StoredImageRef {
  source_url: string;
  bucket?: string;
  object_name?: string;
  url: string;
}

export interface ListingOptimizeStoreOption {
  store_name: string;
  country_code: string;
  msku: string;
  total_amount?: number | null;
  traffic?: number | null;
}

export interface ListingOptimizeRecord {
  id: number;
  asin: string;
  marketplace: string;
  store_name: string;
  country_code: string;
  sku: string;
  optimization_reason: string;
  optimization_direction: string;
  remark: string;
  before_listing: OptimizedListing;
  after_listing: OptimizedListing;
  before_images: StoredImageRef[];
  after_images: StoredImageRef[];
  before_metrics: ListingOptimizeMetricSnapshot;
  current_metrics: ListingOptimizeMetricSnapshot;
  metric_period_days: number;
  metric_start: string;
  metric_end: string;
  current_metric_start: string;
  current_metric_end: string;
  variant_rank?: number | null;
  variant_total?: number | null;
  source_memory_id?: number | null;
  operator: string;
  updated_by: string;
  extra?: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface MemoryFeedbackResponse {
  success: boolean;
  memory_id: number;
  message?: string;
}

export interface DimensionScore {
  subtotal: number;
  [key: string]: number;
}

export interface EvaluateScores {
  cosmo: DimensionScore;
  keywords: DimensionScore;
  rufus: DimensionScore;
  idq: DimensionScore;
  total: number;
}

export interface DimensionAnalysis {
  summary: string;
  strengths: string[];
  weaknesses: string[];
  suggestions: string[];
  [key: string]: unknown;
}

export interface EvaluateAnalysis {
  cosmo: DimensionAnalysis;
  keywords: DimensionAnalysis;
  rufus: DimensionAnalysis;
  idq: DimensionAnalysis;
}

export interface ListingAnalyzeResponse {
  asin: string;
  marketplace: string;
  product: ProductData;
  analysis: string;
  score?: number;
  scores?: EvaluateScores;
  evaluate_analysis?: EvaluateAnalysis;
  overall_summary?: string;
  priority_actions?: string[];
  error?: string;
}

export interface ListingDeepDiagnosticSection {
  summary: string;
  strengths: string[];
  weaknesses: string[];
  suggestions: string[];
}

export interface ListingDeepComparisonSection {
  summary: string;
  own_advantages: string[];
  own_disadvantages: string[];
  competitor_advantages: string[];
  competitor_disadvantages: string[];
  negative_review_gap: string[];
  sales_comparison: string;
  product_potential: string;
  suggestions: string[];
}

export interface ListingCompetitorDiagnosticSection {
  competitor_label: string;
  competitor_asin: string;
  competitor_title: string;
  competitor_brand: string;
  competitor_image: string;
  competitor_monthly_sales_text: string;
  competitor_bsr_rank: string;
  summary: string;
  image_comparison: string;
  brand_comparison: string;
  review_comparison: string;
  listing_comparison: string;
  title_comparison: string;
  scenario_comparison: string;
  sales_comparison: string;
  own_advantages: string[];
  own_disadvantages: string[];
  competitor_advantages: string[];
  competitor_disadvantages: string[];
  suggestions: string[];
  raw_output?: string;
}

export interface ListingDeepDiagnosticResponse {
  asin: string;
  marketplace: string;
  self_diagnosis: ListingDeepDiagnosticSection;
  comparison_diagnosis: ListingDeepComparisonSection;
  competitor_diagnoses: ListingCompetitorDiagnosticSection[];
  raw_output?: string;
  error?: string;
}

export interface TaskSubmitResponse {
  task_id: string;
}

export interface TaskStatusResponse {
  task_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  action: 'optimize' | 'analyze' | 'discover_competitors' | 'market_analysis' | 'review_analysis' | 'fetch_product' | 'fetch_reviews';
  result?: ListingOptimizeResponse | ListingAnalyzeResponse | null;
  /** 运行中的阶段性产出（多候选优化边跑边推送） */
  partial_result?: {
    phase?: 'init' | 'generate' | 'evaluate' | 'done';
    total: number;
    generated: number;
    evaluated: number;
    variants: OptimizedVariant[];
  } | null;
  error?: string;
  elapsed_ms?: number;
  created_at?: string;
  asin?: string;
  marketplace?: string;
}

export interface STIChatResponse {
  session_id: string;
  intent: string;
  query: string;
  sql?: string;
  matched_tables: Record<string, unknown>[];
  data?: Record<string, unknown>;
  analysis?: string;
  error?: string;
  attempts: number;
}

export interface AvailableModel {
  id: string;
  provider: string;
  provider_name: string;
  model: string;
  is_primary: boolean;
}

/** GET /admin/api/pool/models — 仅含已通过模型池验证的模型 */
export interface PoolModelsPayload {
  models: AvailableModel[];
  last_full_test: string | null;
}

export function parsePoolModelsPayload(data: unknown): PoolModelsPayload {
  if (Array.isArray(data)) {
    return { models: data as AvailableModel[], last_full_test: null };
  }
  const o = data as PoolModelsPayload;
  return {
    models: Array.isArray(o?.models) ? o.models : [],
    last_full_test: o?.last_full_test ?? null,
  };
}

export interface ListingRefineResponse {
  asin: string;
  marketplace: string;
  optimized: OptimizedListing;
  error?: string;
}

export interface ListingEmbedResponse {
  success: boolean;
  message: string;
  collection: string;
  insert_count: number;
}

export interface PromptDefaults {
  core_capabilities: string;
  company_info: string;
  bullet_rules: string;
  description_rules: string;
}

export const listingApi = {
  health: () => api.get('/lsta/health'),
  promptDefaults: () => api.get<PromptDefaults>('/lsta/prompt-defaults'),
  fetch: (data: { asin: string; marketplace: string }) =>
    api.post<ProductData>('/lsta/fetch', data),
  fetchWithDiagnostics: (data: { asin: string; marketplace: string }) =>
    api.post<FetchDiagnosticsResponse>('/lsta/fetch-with-diagnostics', data),
  triDimDiagnosticSql: (data: TriDimDiagnosticSqlRequest) =>
    api.post<TriDimDiagnosticSqlResponse>('/lsta/tri-dim-diagnostic-sql', data),
  syncSpAdInsights: (data: { days?: number; asin?: string; limit_per_type?: number }) =>
    api.post('/lsta/sp-ad-insights/sync', data),
  spAdInsights: (data: { asin: string; store_name?: string; days?: number; limit?: number }) =>
    api.post<SpAdInsightResponse>('/lsta/sp-ad-insights', data),
  optimize: (data: {
    asin: string;
    marketplace: string;
    target_keywords?: string[];
    target_audience?: string;
    language?: string;
    session_id?: string;
    model?: string;
    /** 多候选评分阶段使用的模型；空则回退到 model */
    eval_model?: string;
    prompt_overrides?: Partial<PromptDefaults>;
    product_data?: ProductData;
    optimize_sections?: string[];
    competitor_products?: ProductData[];
    enable_fab?: boolean;
    review_analysis?: ReviewAnalysisResult | null;
    sp_ad_insights?: SpAdInsightItem[];
    /** 候选数量（1-10），>1 启用并行多候选 + 曝光/转化加权评分择优 */
    variant_count?: number;
    /** 产品颜色（如 Pink），留空时后端自动从 leang_product_info.colour 查询 */
    color?: string;
    /** 三维诊断指标（来自 fetch 阶段），用于决定曝光/转化评分的加权比重 */
    tri_dim?: TriDimDiagnostic | null;
  }) => api.post<ListingOptimizeResponse>('/lsta/optimize', data),
  createOptimizeRecord: (data: {
    asin: string;
    marketplace: string;
    store_name?: string;
    country_code?: string;
    sku?: string;
    optimization_reason?: string;
    optimization_direction?: string;
    remark?: string;
    before_listing: OptimizedListing;
    after_listing: OptimizedListing;
    before_images?: string[];
    after_images?: string[];
    metric_period_days?: number;
    variant_rank?: number | null;
    variant_total?: number | null;
    source_memory_id?: number | null;
    extra?: Record<string, any>;
  }) => api.post<{ success: boolean; id: number; record: ListingOptimizeRecord }>('/lsta/listing-optimize-records', data),
  optimizeRecords: (data: { asin?: string; marketplace?: string; limit?: number }) =>
    api.post<{ items: ListingOptimizeRecord[] }>('/lsta/listing-optimize-records/list', data),
  optimizeRecordDetail: (data: { id: number }) =>
    api.post<ListingOptimizeRecord>('/lsta/listing-optimize-records/detail', data),
  updateOptimizeRecordRemark: (data: { id: number; remark: string }) =>
    api.post<{ success: boolean; record: ListingOptimizeRecord }>('/lsta/listing-optimize-records/remark', data),
  updateOptimizeRecordStore: (data: { id: number; store_name: string; country_code?: string; sku?: string }) =>
    api.post<{ success: boolean; record: ListingOptimizeRecord }>('/lsta/listing-optimize-records/store', data),
  optimizeRecordStoreOptions: (data: { asin: string }) =>
    api.post<{ items: ListingOptimizeStoreOption[] }>('/lsta/listing-optimize-records/store-options', data),
  deleteOptimizeRecord: (data: { id: number }) =>
    api.post<{ success: boolean; id: number }>('/lsta/listing-optimize-records/delete', data),
  analyze: (data: {
    asin: string; marketplace: string; search_terms?: string;
    session_id?: string; model?: string;
    product_data?: ProductData;
  }) => api.post<ListingAnalyzeResponse>('/lsta/analyze', data),
  deepDiagnostic: (data: {
    asin: string;
    marketplace: string;
    model?: string;
    product_data: ProductData;
    current_title: string;
    current_bullet_points: string[];
    current_description: string;
    current_search_terms?: string;
    review_analysis?: ReviewAnalysisResult | null;
    competitor_products?: ProductData[];
  }) => api.post<ListingDeepDiagnosticResponse>('/lsta/deep-diagnostic', data),
  embed: (data: {
    asin: string;
    marketplace: string;
    title: string;
    bullet_points: string[];
    description: string;
    search_terms: string;
  }) => api.post<ListingEmbedResponse>('/lsta/embed', data),
  /** 提交用户对一条优化结果的反馈（点赞/差劲/评论 → llm_memory） */
  submitFeedback: (data: {
    memory_id: number;
    liked?: boolean | null;
    disliked?: boolean | null;
    comment?: string | null;
  }) => api.post<MemoryFeedbackResponse>('/lsta/memory/feedback', data),
  refine: (data: {
    asin: string;
    marketplace: string;
    current_title: string;
    current_bullet_points: string[];
    current_description: string;
    current_search_terms: string;
    user_feedback: string;
    session_id?: string;
    model?: string;
  }) => api.post<ListingRefineResponse>('/lsta/refine', data),
  lingxingStatus: () => api.get<{ configured: boolean }>('/lsta/lingxing/status'),
  submitToLingxing: (data: {
    asin: string;
    marketplace: string;
    title: string;
    bullet_points: string[];
    description: string;
    search_terms: string;
  }) => api.post<{ success: boolean; message: string; detail?: any }>('/lsta/submit-to-lingxing', data),
  checkTrafficWords: (data: {
    words?: string[];
    title?: string;
    bullet_points?: string[];
    description?: string;
    search_terms?: string;
    target_keywords?: string[];
    product_title?: string;
    product_category?: string;
  }) => api.post<{ word_analysis: WordAnalysis; error?: string }>('/lsta/check-traffic-words', data),
  applyTrafficDecisions: (data: {
    asin: string;
    marketplace: string;
    decisions: Record<string, boolean>;
    replacements?: Record<string, string>;
    current_title: string;
    current_bullet_points: string[];
    current_description: string;
    current_search_terms: string;
    session_id?: string;
    model?: string;
  }) => api.post<ListingRefineResponse>('/lsta/apply-traffic-decisions', data),
  submitTask: (data: {
    action: 'optimize' | 'analyze' | 'discover_competitors' | 'market_analysis' | 'review_analysis' | 'fetch_product' | 'fetch_reviews';
    optimize_params?: Record<string, any>;
    analyze_params?: Record<string, any>;
    competitor_params?: Record<string, any>;
    market_analysis_params?: Record<string, any>;
    review_analysis_params?: Record<string, any>;
    fetch_params?: Record<string, any>;
  }) => api.post<TaskSubmitResponse>('/lsta/task/submit', data),
  getTaskStatus: (taskId: string) =>
    api.get<TaskStatusResponse>(`/lsta/task/${taskId}`),
  listTasks: () =>
    api.get<{ tasks: TaskStatusResponse[] }>('/lsta/tasks'),
  deleteTask: (taskId: string) =>
    api.delete(`/lsta/task/${taskId}`),
  searchTermRecommend: (data: {
    asin: string;
    relevance_filter?: string | null;
  }) => api.post<SearchTermRecommendResponse>('/lsta/search-term-recommend', data),
  /** 单个词 SQR 搜索量（勿循环批量调用） */
  sqrSearchVolume: (data: { term: string }) =>
    api.post<SqrSearchVolumeResponse>('/lsta/sqr-search-volume', data),
  /** 批量 SQR（每请求≤500词，单次分组 SQL），用于搜索词库列表 */
  sqrSearchVolumes: (data: { terms: string[] }) =>
    api.post<SqrSearchVolumesResponse>('/lsta/sqr-search-volumes', data),
  /** 评论分析 */
  reviewAnalysis: (data: {
    asin?: string; marketplace?: string; product_title?: string;
    reviews: ReviewItem[]; model?: string;
  }) => api.post<ReviewAnalysisResponse>('/lsta/review-analysis', data),
  /** 竞品发现（通过 Amazon 搜索） */
  discoverCompetitors: (data: {
    asin: string; marketplace?: string;
    /** 已获取的本品数据；传给后端后可跳过竞品发现前的本品重复抓取 */
    product_data?: ProductData;
    price_tolerance?: number; max_results?: number;
    /** 是否并发拉取竞品完整 ProductData（bullet/description 用于差异化） */
    with_details?: boolean;
    /** 搜索关键词附加的颜色（如 Pink），留空时后端自动从 leang_product_info.colour 查询 */
    color?: string;
  }) => api.post<CompetitorDiscoveryResponse>('/lsta/discover-competitors', data),
  /** 市场分析（输入方向词，抓 Amazon 样本并生成洞察） */
  marketAnalysis: (data: {
    keyword: string; marketplace?: string; max_results?: number; max_pages?: number;
    with_details?: boolean; model?: string;
  }) => api.post<MarketAnalysisResponse>('/lsta/market-analysis', data),
  adStrategyAnalyze: (data: {
    asin?: string; sku?: string; store_name?: string; country_code?: string;
    days?: number; feedback_days?: number; limit?: number;
  }) => api.post<AdStrategyAnalyzeResponse>('/lsta/ad-strategy/analyze', data),
  createAdStrategyAction: (data: Record<string, any>) =>
    api.post<{ success: boolean; action_id: number; table: string }>('/lsta/ad-strategy/actions', data),
  adStrategyFeedback: (data: { action_id?: number; asin?: string; days?: number }) =>
    api.post<{ items: any[] }>('/lsta/ad-strategy/feedback', data),
  /** 批量翻译（hover 中文翻译用；单次 ≤20 条） */
  /** 翻译固定走后端 gpt-4o-mini；preferred_model 已忽略 */
  translate: (data: {
    texts: string[];
    target_lang?: string;
    source_lang?: string;
    preferred_model?: string;
  }) => api.post<TranslateResponse>('/lsta/translate', data),
};

export interface TranslateResponse {
  translations: string[];
  target_lang: string;
  model: string;
}

export interface SearchTermRecommendItem {
  search_term: string;
  relevance: string;
  total_score: number | null;
  size_score: number | null;
  color_score: number | null;
  pattern_score: number | null;
  style_score: number | null;
}

export interface SearchTermRecommendResponse {
  success: boolean;
  message: string;
  msku_info: { msku: string; store_name: string }[];
  matched_msku: string | null;
  matched_store: string | null;
  matched_dir_store: string | null;
  matched_file: string | null;
  summary: Record<string, number>;
  total_unique: number;
  returned_count: number;
  search_terms: SearchTermRecommendItem[];
}

/** POST /lsta/sqr-search-volume — 悬停按需查 SQR 搜索量 */
export interface SqrSearchVolumeResponse {
  term: string;
  total_search_count: number;
  grade: string;
  grade_label: string;
  since_date: string;
  cached?: boolean;
}

export interface SqrSearchVolumesResponse {
  volumes: Record<string, SqrSearchVolumeResponse>;
}

export interface PainPoint {
  title: string; detail: string; frequency: string; related_reviews: number[];
}
export interface SellingPoint {
  title: string; detail: string; frequency: string; related_reviews: number[];
}
export interface CoreFeature {
  title: string; detail: string; sentiment: string;
}
export interface ReviewAnalysisResult {
  pain_points: PainPoint[];
  selling_points: SellingPoint[];
  core_features: CoreFeature[];
  overall_sentiment: string;
  summary: string;
}
export interface ReviewAnalysisResponse {
  asin: string; marketplace: string; review_count: number;
  analysis: ReviewAnalysisResult | null;
  error?: string;
}

export interface CompetitorItem {
  asin: string; title: string; price: string; currency: string;
  rating: string; review_count: string; image: string;
  avg_price: number | null;
  /** BSR 排名（with_details=true 时来自 product_data.bsr_rank） */
  bsr_rank?: string;
  /** 维度抽取（从 title/proxy 字段解析） */
  color?: string;
  size?: string;
  style?: string;
  /** with_details=true 时填充，含完整 bullet_points / description */
  product_data?: ProductData | null;
}
export interface CompetitorDiscoveryResponse {
  source_asin: string; source_category_2: string;
  source_avg_price: number | null; source_total_volume: any;
  competitors: CompetitorItem[];
  total_found: number;
  /** 供前端勾选过滤的可用维度（已按频次倒序） */
  available_colors?: string[];
  available_sizes?: string[];
  available_styles?: string[];
  error?: string;
}

export interface MarketProductItem {
  asin: string;
  title: string;
  brand: string;
  price: string;
  currency: string;
  rating: string;
  review_count: string;
  image: string;
  avg_price: number | null;
  bsr_rank: string;
  monthly_sales_text: string;
  product_url: string;
}

export interface MarketBrandStat {
  brand: string;
  count: number;
  avg_rating: number | null;
  total_reviews: number;
  sample_asins: string[];
  description: string;
}

export interface MarketPriceBand {
  label: string;
  count: number;
  min_price: number | null;
  max_price: number | null;
}

export interface MarketAnalysisInsight {
  hot_directions: string[];
  review_pain_points: string[];
  accessible_markets: string[];
  market_capacity: string;
  leading_brands: string[];
  market_trends: string[];
  top_tk_designers: string[];
  opportunities: string[];
  risks: string[];
  summary: string;
}

export interface MarketAnalysisResponse {
  keyword: string;
  marketplace: string;
  search_keywords: string[];
  total_found: number;
  analyzed_count: number;
  avg_price: number | null;
  avg_rating: number | null;
  total_reviews: number;
  top_products: MarketProductItem[];
  top_brands: MarketBrandStat[];
  price_bands: MarketPriceBand[];
  insight: MarketAnalysisInsight;
  raw_notes: string[];
  error?: string | null;
}

export interface AdStrategyMetrics {
  impressions: number;
  clicks: number;
  cost: number;
  orders: number;
  sales: number;
  units: number;
  ctr: number;
  cpc: number;
  cvr: number;
  acos: number;
  roas: number;
  [key: string]: any;
}

export interface AdStrategyActionSuggestion {
  action_type: string;
  entity_type: string;
  entity_value: string;
  asin: string;
  sku: string;
  store_name: string;
  country_code: string;
  profile_id: string;
  campaign_id: string;
  campaign_name: string;
  ad_group_id: string;
  ad_group_name: string;
  before_value: string;
  after_value: string;
  reason: string;
  feedback_days: number;
  metrics: AdStrategyMetrics;
}

export interface AdStrategyAnalyzeResponse {
  date_start: string;
  date_end: string;
  compare_start: string;
  compare_end: string;
  filters: Record<string, string>;
  current: AdStrategyMetrics;
  previous: AdStrategyMetrics;
  trend: Record<string, number>;
  product_rows: AdStrategyMetrics[];
  search_terms: AdStrategyMetrics[];
  keywords: AdStrategyMetrics[];
  purchased_asins: AdStrategyMetrics[];
  recommended_actions: AdStrategyActionSuggestion[];
  action_feedback: any[];
  target_table: string;
}

export interface LAACandidateItem {
  name: string;
  reason: string;
  score: number;
}

export interface LAAMatchResult {
  best_audience: string;
  best_scene: string;
  audience_candidates: LAACandidateItem[];
  scene_candidates: LAACandidateItem[];
  best_selling_point?: string;
  best_selling_point_reason?: string;
  best_selling_point_score?: number;
  best_selling_point_candidates?: LAACandidateItem[];
  insight: string;
}

export interface LAAMatchResponse {
  status: string;
  result: LAAMatchResult;
  raw_output: string;
}

export interface SQLExecResponse {
  columns: string[];
  rows: Record<string, any>[];
  row_count: number;
  error?: string;
}

const RESTRICTION_FIELD_ALIASES: Record<string, string[]> = {
  store_name: ['store_name', '店铺'],
  brand: ['brand', '品牌'],
  salesman: ['salesman', '运营'],
  category_2: ['category_2', '类目'],
  country_code: ['country_code', '国家'],
  sales_apartment: ['sales_apartment', '部门', '销售部门'],
};

function getLocalDataRestrictions(): Record<string, string[]> | null {
  try {
    const raw = localStorage.getItem('leang_user_info');
    const restrictions = raw ? JSON.parse(raw)?.data_restrictions : null;
    return restrictions && typeof restrictions === 'object' ? restrictions : null;
  } catch {
    return null;
  }
}

export function hasLocalDataRestrictions(): boolean {
  const restrictions = getLocalDataRestrictions();
  return !!restrictions && Object.values(restrictions).some(v => Array.isArray(v) && v.length > 0);
}

function normalizeRestrictionValue(value: unknown): string {
  return String(value ?? '')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '');
}

function restrictionValueMatches(rowValue: unknown, allowed: Set<string>): boolean {
  const current = normalizeRestrictionValue(rowValue);
  if (!current) return false;
  if (allowed.has(current)) return true;
  for (const item of allowed) {
    if (item && (current.includes(item) || item.includes(current))) return true;
  }
  return false;
}

export function applyLocalDataRestrictions(data: SQLExecResponse): SQLExecResponse {
  if (!data?.rows?.length || data.error) return data;
  const restrictions = getLocalDataRestrictions();
  if (!restrictions) return data;

  const normalized = Object.entries(restrictions)
    .filter(([, values]) => Array.isArray(values) && values.length > 0)
    .map(([field, values]) => ({
      aliases: RESTRICTION_FIELD_ALIASES[field] || [field],
      allowed: new Set(values.map(v => normalizeRestrictionValue(v)).filter(Boolean)),
    }))
    .filter(item => item.allowed.size > 0);

  if (!normalized.length) return data;

  const rows = data.rows.filter(row => normalized.every(item => {
    const key = item.aliases.find(alias => Object.prototype.hasOwnProperty.call(row, alias));
    if (!key) return true;
    const value = row[key];
    return restrictionValueMatches(value, item.allowed);
  }));

  return {
    ...data,
    rows,
    row_count: rows.length,
  };
}

export const stiApi = {
  health: () => api.get('/lda/health'),
  chat: (data: {
    session_id: string;
    message: string;
    user_id?: string;
    model?: string;
    data_restrictions?: Record<string, string[]> | null;
  }) => api.post<STIChatResponse>('/lda/chat', data),
  tables: (keyword: string) => api.get(`/lda/tables?keyword=${encodeURIComponent(keyword)}`),
  execSql: (sql: string) => api.post<SQLExecResponse>('/lda/sql', { sql }).then(res => ({
    ...res,
    data: applyLocalDataRestrictions(res.data),
  })),
};

export const laaApi = {
  health: () => api.get('/laa/health'),
  match: (data: {
    image_url?: string;
    image_base64?: string;
    comment: string;
    color: string;
    size: string;
    model?: string;
  }) => api.post<LAAMatchResponse>('/laa/match', data),
};

export interface LMAChatResponse {
  session_id: string;
  answer: string;
  sources?: { source: string; content: string }[];
  error?: string;
}

export interface ChunkPreview {
  index: number;
  length: number;
  content: string;
}

export interface PreviewChunksResponse {
  file_name: string;
  total_chars: number;
  chunk_count: number;
  chunk_strategy: string;
  chunk_size: number;
  chunk_overlap: number;
  chunks: ChunkPreview[];
}

export interface MilvusCollection {
  name: string;
  num_entities: number;
  description: string;
}

export interface CollectionDetail {
  name: string;
  num_entities: number;
  description: string;
  fields: { name: string; dtype: string; is_primary: boolean; params?: Record<string, unknown> }[];
}

export const lmaApi = {
  health: () => api.get('/lma/health'),
  chat: (data: { session_id: string; question: string; collection_name?: string; model?: string }) =>
    api.post<LMAChatResponse>('/lma/chat', data),
  previewChunks: (formData: FormData) =>
    api.post('/lma/preview-chunks', formData, { headers: { 'Content-Type': 'multipart/form-data' } }),
  ingest: (formData: FormData) =>
    api.post('/lma/ingest', formData, { headers: { 'Content-Type': 'multipart/form-data' } }),
  collections: () => api.get('/lma/collections'),
  collectionDetail: (name: string) => api.get(`/lma/collection/${name}`),
  collectionData: (name: string, offset: number, limit: number) =>
    api.get(`/lma/collection/${name}/data?offset=${offset}&limit=${limit}`),
  dropCollection: (name: string) => api.delete(`/lma/collection/${name}`),
};

export interface LstaStats {
  optimize_count: number;
  refine_count: number;
  liked_count: number;
  disliked_count: number;
  comment_count: number;
  total_lsta: number;
}

export const adminApi = {
  health: () => api.get('/admin/api/dashboard'),
  dashboard: () => api.get('/admin/api/dashboard'),
  modelPool: () => api.get('/admin/api/pool/status'),
  availableModels: () => api.get<PoolModelsPayload | AvailableModel[]>('/admin/api/pool/models'),
  lstaStats: () => api.get<LstaStats>('/admin/api/lsta/stats'),
};

export default api;
