import { apiClient, get, post, put, del, patch } from "@/lib/api/client"
import type {
  ActiveFilter,
  Analysis,
  ComparisonPlan,
  ComparisonResult,
  EvidenceEntries,
  EvidenceEntryRequest,
  AnalysisListItem,
  AnalysisStatus,
  CreateCombinedAnalysisRequest,
  CreateAnalysisRequest,
  DashboardAction,
  DashboardPalette,
  DashboardState,
  LiveQueryResponse,
  MetricDefinition,
  MetricDefinitionInput,
  MetricPreview,
  PaginatedResponse,
  RecommendationFeedbackResponse,
  RecommendationFeedbackVerdict,
  ShareLinkResponse,
} from "@/types"

const ANALYSIS_CREATE_TIMEOUT_MS = 10 * 60 * 1000

export const analysesApi = {
  entries(id: string, request: EvidenceEntryRequest): Promise<EvidenceEntries> {
    return post(`/analyses/${id}/entries`, request)
  },
  compare(id: string, plan: ComparisonPlan): Promise<ComparisonResult> {
    return post(`/analyses/${id}/compare`, plan)
  },
  list(params?: {
    page?: number
    limit?: number
    search?: string
    status?: string
  }): Promise<PaginatedResponse<AnalysisListItem>> {
    return get("/analyses", { params })
  },

  get(id: string): Promise<Analysis> {
    return get(`/analyses/${id}`)
  },

  create(data: CreateAnalysisRequest): Promise<Analysis> {
    return post("/analyses", data, { timeout: ANALYSIS_CREATE_TIMEOUT_MS })
  },

  createCombined(data: CreateCombinedAnalysisRequest): Promise<Analysis> {
    return post("/analyses/combined", data, { timeout: ANALYSIS_CREATE_TIMEOUT_MS })
  },

  delete(id: string): Promise<void> {
    return del(`/analyses/${id}`)
  },

  rename(id: string, name: string): Promise<Analysis> {
    return patch(`/analyses/${id}`, { name })
  },

  refreshSummary(id: string): Promise<{ summary: string; analysis_evidence: Record<string, unknown> }> {
    return post(`/analyses/${id}/summary/refresh`)
  },

  rerun(id: string): Promise<Analysis> {
    return post(`/analyses/${id}/rerun`, undefined, {
      timeout: ANALYSIS_CREATE_TIMEOUT_MS,
    })
  },

  getStatus(id: string): Promise<{ status: AnalysisStatus; progress: number; error?: string }> {
    return get(`/analyses/${id}/status`)
  },

  queryAnalysis(id: string, filters: ActiveFilter[]): Promise<LiveQueryResponse> {
    return post(`/analyses/${id}/query`, {
      filters: filters.map((f) => ({ column: f.column, op: f.op, values: f.values })),
    })
  },

  listMetrics(id: string): Promise<MetricDefinition[]> {
    return get(`/analyses/${id}/metrics`)
  },

  previewMetric(id: string, definition: MetricDefinitionInput): Promise<MetricPreview> {
    return post(`/analyses/${id}/metrics/preview`, definition)
  },

  approveMetric(id: string, definition: MetricDefinitionInput): Promise<MetricDefinition> {
    return post(`/analyses/${id}/metrics`, definition)
  },

  reviseMetric(id: string, familyId: string, definition: MetricDefinitionInput): Promise<MetricDefinition> {
    return put(`/analyses/${id}/metrics/${familyId}`, definition)
  },

  getDashboard(id: string): Promise<DashboardState> {
    return get(`/analyses/${id}/dashboard`)
  },

  editDashboard(id: string, expectedVersion: number, action: DashboardAction, chartId?: string,
    metricFamilyId?: string, filters?: ActiveFilter[], palette?: DashboardPalette): Promise<DashboardState> {
    return post(`/analyses/${id}/dashboard`, {
      expected_version: expectedVersion, action, chart_id: chartId ?? null,
      metric_family_id: metricFamilyId ?? null,
      palette: palette ?? null,
      filters: filters?.map(({ column, op, values }) => ({ column, op, values })) ?? null,
    })
  },

  async downloadCleaned(id: string): Promise<Blob> {
    const res = await apiClient.get<Blob>(`/analyses/${id}/cleaned-download`, {
      responseType: "blob",
      timeout: 120_000,
    })
    return res.data
  },

  async downloadProfileJson(id: string): Promise<Blob> {
    const res = await apiClient.get<Blob>(`/analyses/${id}/profile-json`, {
      responseType: "blob",
      timeout: 120_000,
    })
    return res.data
  },

  async downloadPdf(id: string): Promise<Blob> {
    const res = await apiClient.get<Blob>(`/analyses/${id}/export/pdf`, {
      responseType: "blob",
      timeout: 120_000,
    })
    return res.data
  },

  async downloadExcel(id: string): Promise<Blob> {
    const res = await apiClient.get<Blob>(`/analyses/${id}/export/excel`, {
      responseType: "blob",
      timeout: 120_000,
    })
    return res.data
  },

  createShareLink(id: string): Promise<ShareLinkResponse> {
    return post<ShareLinkResponse>(`/analyses/${id}/share`, undefined)
  },

  revokeShareLink(id: string): Promise<void> {
    return del<void>(`/analyses/${id}/share`)
  },

  setRecommendationFeedback(
    analysisId: string,
    insightId: string,
    verdict: RecommendationFeedbackVerdict
  ): Promise<RecommendationFeedbackResponse> {
    return put<RecommendationFeedbackResponse>(
      `/analyses/${analysisId}/insights/${insightId}/feedback`,
      { verdict }
    )
  },

  clearRecommendationFeedback(analysisId: string, insightId: string): Promise<void> {
    return del<void>(`/analyses/${analysisId}/insights/${insightId}/feedback`)
  },
}
