import axios, { type AxiosInstance, type AxiosRequestConfig } from "axios"
import { createClient } from "@/lib/supabase/client"

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

function createApiClient(): AxiosInstance {
  const instance = axios.create({
    baseURL: `${BASE_URL}/api/v1`,
    headers: {
      "Content-Type": "application/json",
    },
    timeout: 30_000,
  })

  // Attach Supabase access token to every request
  instance.interceptors.request.use(async (config) => {
    const supabase = createClient()
    const {
      data: { session },
    } = await supabase.auth.getSession()
    if (session?.access_token) {
      config.headers.Authorization = `Bearer ${session.access_token}`
    }
    return config
  })

  // Surface 401s to the caller. Do not sign out of Supabase here: a backend
  // token/config problem should not destroy the browser auth session.
  instance.interceptors.response.use(
    (response) => response,
    async (error) => {
      return Promise.reject(error)
    }
  )

  return instance
}

export const apiClient = createApiClient()

// Generic typed request helpers
export async function get<T>(
  path: string,
  config?: AxiosRequestConfig
): Promise<T> {
  const res = await apiClient.get<T>(path, config)
  return res.data
}

export async function post<T>(
  path: string,
  data?: unknown,
  config?: AxiosRequestConfig
): Promise<T> {
  const res = await apiClient.post<T>(path, data, config)
  return res.data
}

export async function put<T>(
  path: string,
  data?: unknown,
  config?: AxiosRequestConfig
): Promise<T> {
  const res = await apiClient.put<T>(path, data, config)
  return res.data
}

export async function patch<T>(
  path: string,
  data?: unknown,
  config?: AxiosRequestConfig
): Promise<T> {
  const res = await apiClient.patch<T>(path, data, config)
  return res.data
}

export async function del<T>(
  path: string,
  config?: AxiosRequestConfig
): Promise<T> {
  const res = await apiClient.delete<T>(path, config)
  return res.data
}
