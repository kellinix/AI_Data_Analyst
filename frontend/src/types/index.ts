// ============================================================
// Shared TypeScript Types
// ============================================================

// ---- Pagination --------------------------------------------
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  limit: number
  pages: number
}

// ---- User --------------------------------------------------
export interface User {
  id: string
  email: string
  full_name: string | null
  avatar_url: string | null
  plan: SubscriptionPlan
  created_at: string
  updated_at: string
}

export type SubscriptionPlan = "free" | "starter" | "professional" | "enterprise"

export interface UserProfile extends User {
  subscription: Subscription | null
  usage: UsageStats
}

export interface UsageStats {
  analyses_this_month: number
  analyses_limit: number
  storage_used_bytes: number
  storage_limit_bytes: number
  ai_queries_this_month: number
  ai_queries_limit: number
}

// ---- Subscription ------------------------------------------
export interface Subscription {
  id: string
  user_id: string
  plan: SubscriptionPlan
  status: "active" | "canceled" | "past_due" | "trialing"
  current_period_start: string
  current_period_end: string
  cancel_at_period_end: boolean
  stripe_subscription_id: string | null
  created_at: string
}

// ---- File Upload -------------------------------------------
export interface UploadedFile {
  id: string
  user_id: string
  filename: string
  original_filename: string
  file_size: number
  mime_type: string
  storage_path: string
  row_count: number | null
  column_count: number | null
  columns: ColumnInfo[] | null
  created_at: string
}

export interface ColumnInfo {
  name: string
  dtype: string
  non_null_count: number
  null_count: number
  unique_count: number
  sample_values: unknown[]
}

// ---- Analysis ----------------------------------------------
export type AnalysisStatus = "pending" | "processing" | "completed" | "failed"

export interface AnalysisListItem {
  id: string
  name: string
  status: AnalysisStatus
  file_id: string
  filename: string
  row_count: number
  column_count: number
  created_at: string
  updated_at: string
}

export interface Analysis extends AnalysisListItem {
  insights: Insight[]
  charts: ChartConfig[]
  summary: string | null
  error_message: string | null
  metadata: Record<string, unknown>
  share_token: string | null
  filterable_columns: FilterableColumn[]
}

// ---- Interactive filtering / slicers ------------------------
export interface FilterableColumn {
  column: string
  display_label: string
  role: string
  kind: "categorical" | "numeric"
  unique_count?: number | null
  top_values?: { value: string; count: number }[] | null
  min?: number | null
  max?: number | null
}

export type FilterOp = "in" | "between"

export interface ActiveFilter {
  column: string
  display_label: string
  op: FilterOp
  values: (string | number)[]
}

export interface ChartPatch {
  id: string
  echarts_option: Record<string, unknown>
  visual_spec?: Record<string, unknown> | null
  skipped: boolean
}

export interface KpiPatch {
  insight_id: string
  value: number | null
  skipped: boolean
}

export interface LiveQueryResponse {
  row_count: number
  sample_row_count: number
  charts: ChartPatch[]
  kpis: KpiPatch[]
}

export interface ShareLinkResponse {
  share_token: string
  share_url: string
}

export interface SharedAnalysis {
  name: string
  row_count: number | null
  column_count: number | null
  created_at: string
  summary: string | null
  insights: Insight[]
  charts: ChartConfig[]
}

export interface CreateAnalysisRequest {
  file_id: string
  name?: string
  relationship_context?: Record<string, unknown>
  cleaning?: CleaningOptions
}

export interface CreateCombinedAnalysisRequest {
  file_ids: string[]
  name?: string
  relationship_context?: Record<string, unknown>
  cleaning?: CleaningOptions
}

export interface CleaningOptions {
  mode: "clean" | "raw"
  remove_duplicates?: boolean
  fuzzy_deduplicate?: boolean
  standardize_columns?: boolean
  normalize_dates?: boolean
  clean_text?: boolean
  parse_currency_percent?: boolean
  drop_empty?: boolean
  missing_data_strategy?: "smart" | "none"
  outlier_policy?: "keep" | "cap" | "exclude"
  semantic_categorical_merging?: boolean
}

// ---- Insights ----------------------------------------------
export type InsightType =
  | "trend"
  | "anomaly"
  | "correlation"
  | "distribution"
  | "summary"
  | "forecast"
  | "recommendation"

export interface Insight {
  id: string
  analysis_id: string
  type: InsightType
  title: string
  description: string
  importance: "low" | "medium" | "high" | "critical"
  confidence: number // 0-1
  data: Record<string, unknown>
  chart_config: ChartConfig | null
  created_at: string
  // The viewing owner's verdict on a recommendation; absent on shared views.
  user_feedback?: RecommendationFeedbackVerdict | null
}

export type RecommendationFeedbackVerdict = "helpful" | "not_helpful"

export interface RecommendationFeedbackResponse {
  insight_id: string
  verdict: RecommendationFeedbackVerdict
}

// ---- Charts ------------------------------------------------
export type ChartType =
  | "bar"
  | "line"
  | "area"
  | "pie"
  | "donut"
  | "scatter"
  | "heatmap"
  | "histogram"
  | "boxplot"
  | "funnel"

export interface ChartConfig {
  id: string
  type: ChartType
  title: string
  description: string | null
  xAxis: string | null
  yAxis: string | null
  series: string[]
  color_scheme: string[]
  visual_spec?: Record<string, unknown> | null
  echarts_option: Record<string, unknown>
}

// ---- Chat --------------------------------------------------
export type MessageRole = "user" | "assistant" | "system"

export interface ChatMessage {
  id: string
  session_id: string
  role: MessageRole
  content: string
  chart_config: ChartConfig | null
  created_at: string
}

export interface ChatSession {
  id: string
  analysis_id: string
  title: string
  message_count: number
  created_at: string
  updated_at: string
  last_message: ChatMessage | null
}


// ---- API Errors --------------------------------------------
export interface ApiError {
  detail: string
  code?: string
  field?: string
}

// ---- Dashboard Widgets ------------------------------------
export type WidgetSize = "sm" | "md" | "lg" | "xl"

export interface DashboardWidget {
  id: string
  type: "chart" | "stat" | "insight" | "table"
  title: string
  size: WidgetSize
  position: { x: number; y: number }
  config: Record<string, unknown>
}

// ---- Shared Analysis Token ---------------------------------
export interface SharedAnalysis {
  token: string
  analysis_id: string
  analysis: Analysis
  expires_at: string | null
  view_count: number
}
