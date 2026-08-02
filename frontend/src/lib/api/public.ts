import axios from "axios"
import type { SharedAnalysis } from "@/types"

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

const publicClient = axios.create({
  baseURL: `${BASE_URL}/api/v1/public`,
  timeout: 30_000,
})

export const publicApi = {
  getShared(token: string): Promise<SharedAnalysis> {
    return publicClient.get(`/shared/${token}`).then((res) => res.data)
  },
}
