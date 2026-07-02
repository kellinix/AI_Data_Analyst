import axios from "axios"
import { del, post } from "@/lib/api/client"
import { createClient } from "@/lib/supabase/client"
import type { UploadedFile } from "@/types"

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export const uploadsApi = {
  async uploadFile(
    file: File,
    onProgress?: (percent: number) => void
  ): Promise<UploadedFile> {
    const formData = new FormData()
    formData.append("file", file)

    const supabase = createClient()
    const {
      data: { session },
    } = await supabase.auth.getSession()

    const headers: Record<string, string> = {}
    if (session?.access_token) {
      headers.Authorization = `Bearer ${session.access_token}`
    }

    const res = await axios.post<UploadedFile>(
      `${BASE_URL}/api/v1/uploads`,
      formData,
      {
        headers,
        timeout: 120_000,
        onUploadProgress: (progressEvent) => {
          if (progressEvent.total && onProgress) {
            const percent = Math.round(
              (progressEvent.loaded * 100) / progressEvent.total
            )
            onProgress(percent)
          }
        },
      }
    )
    return res.data
  },

  getUploadedFiles(): Promise<UploadedFile[]> {
    return post("/uploads/list")
  },

  deleteFile(id: string): Promise<void> {
    return del(`/uploads/${id}`)
  },
}
