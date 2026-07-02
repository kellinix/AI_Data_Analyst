import type { Metadata } from "next"
import { notFound } from "next/navigation"
import { Suspense } from "react"
import { AnalysisDashboard } from "@/components/analysis/analysis-dashboard"
import { AnalysisDashboardSkeleton } from "@/components/analysis/analysis-dashboard-skeleton"

export const metadata: Metadata = {
  title: "Analysis",
}

export default async function AnalysisPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  if (!id) notFound()

  return (
    <Suspense fallback={<AnalysisDashboardSkeleton />}>
      <AnalysisDashboard id={id} />
    </Suspense>
  )
}
