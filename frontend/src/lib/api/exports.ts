import { get, post } from "@/lib/api/client"
import type { ExportJob } from "@/types"

export const exportsApi = {
  createExport(data: {
    analysis_id: string
    format: "pdf" | "xlsx" | "csv" | "png"
    options?: Record<string, unknown>
  }): Promise<ExportJob> {
    return post("/exports", data)
  },

  getExportStatus(jobId: string): Promise<ExportJob> {
    return get(`/exports/${jobId}`)
  },

  getDownloadUrl(jobId: string): Promise<{ url: string; expires_at: string }> {
    return get(`/exports/${jobId}/download`)
  },
}
