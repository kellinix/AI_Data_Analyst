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
  metadata: Record<string, unknown>
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

// ---- Exports -----------------------------------------------
export type ExportFormat = "pdf" | "xlsx" | "csv" | "png"
export type ExportStatus = "pending" | "processing" | "completed" | "failed"

export interface ExportJob {
  id: string
  analysis_id: string
  format: ExportFormat
  status: ExportStatus
  download_url: string | null
  expires_at: string | null
  file_size: number | null
  error: string | null
  created_at: string
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
