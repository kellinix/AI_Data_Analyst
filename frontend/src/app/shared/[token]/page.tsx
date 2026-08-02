"use client"

import { use } from "react"
import { useQuery } from "@tanstack/react-query"
import { AlertTriangle } from "lucide-react"
import { publicApi } from "@/lib/api/public"
import { SharedAnalysisView } from "@/components/analysis/shared-analysis-view"
import { AnalysisDashboardSkeleton } from "@/components/analysis/analysis-dashboard-skeleton"

export default function SharedAnalysisPage({
  params,
}: {
  params: Promise<{ token: string }>
}) {
  const { token } = use(params)
  const { data: analysis, isLoading, error } = useQuery({
    queryKey: ["shared-analysis", token],
    queryFn: () => publicApi.getShared(token),
    retry: false,
  })

  if (isLoading) return <AnalysisDashboardSkeleton />

  if (error || !analysis) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-8 text-center">
        <AlertTriangle className="h-10 w-10 text-amber-500" />
        <div className="space-y-1">
          <h1 className="text-lg font-semibold text-zinc-900 dark:text-white">
            This share link isn&apos;t available
          </h1>
          <p className="max-w-sm text-sm text-zinc-500">
            It may have been revoked, or the link is incorrect. Ask the person who shared it for a new link.
          </p>
        </div>
      </div>
    )
  }

  return <SharedAnalysisView analysis={analysis} />
}
