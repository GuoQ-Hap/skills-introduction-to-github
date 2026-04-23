import axios from 'axios';

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

export interface FetchDiagnosticsResponse {
  product: ProductData;
  tri_dim: TriDimDiagnostic | null;
  traffic_words: TrafficWordItem[];
  traffic_word_count: number;
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
  error?: string;
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

export interface TaskSubmitResponse {
  task_id: string;
}

export interface TaskStatusResponse {
  task_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  action: 'optimize' | 'analyze';
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
    /** 候选数量（1-10），>1 启用并行多候选 + 曝光/转化加权评分择优 */
    variant_count?: number;
    /** 产品颜色（如 Pink），留空时后端自动从 leang_product_info.colour 查询 */
    color?: string;
    /** 三维诊断指标（来自 fetch 阶段），用于决定曝光/转化评分的加权比重 */
    tri_dim?: TriDimDiagnostic | null;
  }) => api.post<ListingOptimizeResponse>('/lsta/optimize', data),
  analyze: (data: {
    asin: string; marketplace: string; search_terms?: string;
    session_id?: string; model?: string;
    product_data?: ProductData;
  }) => api.post<ListingAnalyzeResponse>('/lsta/analyze', data),
  embed: (data: {
    asin: string;
    marketplace: string;
    title: string;
    bullet_points: string[];
    description: string;
    search_terms: string;
  }) => api.post<ListingEmbedResponse>('/lsta/embed', data),
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
    action: 'optimize' | 'analyze' | 'discover_competitors' | 'review_analysis' | 'fetch_product' | 'fetch_reviews';
    optimize_params?: Record<string, any>;
    analyze_params?: Record<string, any>;
    competitor_params?: Record<string, any>;
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
    price_tolerance?: number; max_results?: number;
    /** 是否并发拉取竞品完整 ProductData（bullet/description 用于差异化） */
    with_details?: boolean;
    /** 搜索关键词附加的颜色（如 Pink），留空时后端自动从 leang_product_info.colour 查询 */
    color?: string;
  }) => api.post<CompetitorDiscoveryResponse>('/lsta/discover-competitors', data),
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

export interface SQLExecResponse {
  columns: string[];
  rows: Record<string, any>[];
  row_count: number;
  error?: string;
}

export const stiApi = {
  health: () => api.get('/lda/health'),
  chat: (data: { session_id: string; message: string; user_id?: string; model?: string }) =>
    api.post<STIChatResponse>('/lda/chat', data),
  tables: (keyword: string) => api.get(`/lda/tables?keyword=${encodeURIComponent(keyword)}`),
  execSql: (sql: string) => api.post<SQLExecResponse>('/lda/sql', { sql }),
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

export const adminApi = {
  health: () => api.get('/admin/api/dashboard'),
  dashboard: () => api.get('/admin/api/dashboard'),
  modelPool: () => api.get('/admin/api/pool/status'),
  availableModels: () => api.get<PoolModelsPayload | AvailableModel[]>('/admin/api/pool/models'),
};

export default api;
