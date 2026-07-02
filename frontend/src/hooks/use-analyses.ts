import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query"
import { analysesApi } from "@/lib/api/analyses"
import type {
  Analysis,
  CreateCombinedAnalysisRequest,
  CreateAnalysisRequest,
} from "@/types"

export const analysisKeys = {
  all: ["analyses"] as const,
  lists: () => [...analysisKeys.all, "list"] as const,
  list: (params: Record<string, unknown>) =>
    [...analysisKeys.lists(), params] as const,
  details: () => [...analysisKeys.all, "detail"] as const,
  detail: (id: string) => [...analysisKeys.details(), id] as const,
  status: (id: string) => [...analysisKeys.all, "status", id] as const,
}

export function useAnalyses(params?: {
  page?: number
  limit?: number
  search?: string
  status?: string
}) {
  return useQuery({
    queryKey: analysisKeys.list(params ?? {}),
    queryFn: () => analysesApi.list(params),
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? []
      return items.some((item) =>
        item.status === "pending" || item.status === "processing"
      )
        ? 3000
        : false
    },
  })
}

export function useAnalysis(
  id: string,
  options?: Partial<UseQueryOptions<Analysis>>
) {
  return useQuery({
    queryKey: analysisKeys.detail(id),
    queryFn: () => analysesApi.get(id),
    enabled: !!id,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === "pending" || status === "processing" ? 2000 : false
    },
    ...options,
  })
}

export function useAnalysisStatus(id: string, enabled = true) {
  return useQuery({
    queryKey: analysisKeys.status(id),
    queryFn: () => analysesApi.getStatus(id),
    enabled: !!id && enabled,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (status === "completed" || status === "failed") return false
      return 2000
    },
  })
}

export function useCreateAnalysis() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateAnalysisRequest) => analysesApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: analysisKeys.lists() })
    },
  })
}

export function useCreateCombinedAnalysis() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateCombinedAnalysisRequest) =>
      analysesApi.createCombined(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: analysisKeys.lists() })
    },
  })
}

export function useDeleteAnalysis() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => analysesApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: analysisKeys.lists() })
    },
  })
}

export function useRenameAnalysis() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      analysesApi.rename(id, name),
    onSuccess: (updated) => {
      queryClient.setQueryData(analysisKeys.detail(updated.id), updated)
      queryClient.invalidateQueries({ queryKey: analysisKeys.lists() })
    },
  })
}

export function useRerunAnalysis() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => analysesApi.rerun(id),
    onSuccess: (updated) => {
      queryClient.setQueryData(analysisKeys.detail(updated.id), updated)
      queryClient.invalidateQueries({ queryKey: analysisKeys.status(updated.id) })
    },
  })
}
