import { apiClient, get, post, del, patch } from "@/lib/api/client"
import type {
  Analysis,
  AnalysisListItem,
  AnalysisStatus,
  CreateCombinedAnalysisRequest,
  CreateAnalysisRequest,
  PaginatedResponse,
} from "@/types"

const ANALYSIS_CREATE_TIMEOUT_MS = 10 * 60 * 1000

export const analysesApi = {
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

  rerun(id: string): Promise<Analysis> {
    return post(`/analyses/${id}/rerun`, undefined, {
      timeout: ANALYSIS_CREATE_TIMEOUT_MS,
    })
  },

  getStatus(id: string): Promise<{ status: AnalysisStatus; progress: number; error?: string }> {
    return get(`/analyses/${id}/status`)
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
}
