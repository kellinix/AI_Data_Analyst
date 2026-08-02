"use client"

import { Lock } from "lucide-react"
import { ExecutiveSummary } from "@/components/analysis/executive-summary"
import { KpiGrid } from "@/components/analysis/kpi-grid"
import { ChartsGrid } from "@/components/analysis/charts-grid"
import { InsightsPanel } from "@/components/analysis/insights-panel"
import { RecommendationsPanel } from "@/components/analysis/recommendations-panel"
import { formatDate } from "@/lib/utils"
import type { SharedAnalysis } from "@/types"

interface SharedAnalysisViewProps {
  analysis: SharedAnalysis
}

export function SharedAnalysisView({ analysis }: SharedAnalysisViewProps) {
  const insights = Array.isArray(analysis.insights) ? analysis.insights : []
  const charts = Array.isArray(analysis.charts) ? analysis.charts : []

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-8 p-8">
      <div className="flex items-center justify-between gap-4 rounded-lg border border-blue-100 bg-blue-50 px-4 py-2.5 text-xs text-blue-700 dark:border-blue-900/40 dark:bg-blue-950/30 dark:text-blue-300">
        <span className="flex items-center gap-1.5">
          <Lock className="h-3.5 w-3.5" />
          Read-only shared view — chat and editing are turned off
        </span>
      </div>

      <div className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight text-zinc-900 dark:text-white">
          {analysis.name}
        </h1>
        <p className="text-sm text-zinc-500">
          {analysis.row_count?.toLocaleString() ?? "—"} rows ·{" "}
          {analysis.column_count ?? "—"} columns · Analysed{" "}
          {formatDate(analysis.created_at)}
        </p>
      </div>

      {analysis.summary && <ExecutiveSummary summary={analysis.summary} />}
      {insights.length > 0 && <KpiGrid insights={insights} />}
      {charts.length > 0 && <ChartsGrid charts={charts} />}
      {insights.length > 0 && <InsightsPanel insights={insights} />}
      {insights.some((i) => i.type === "recommendation") && (
        <RecommendationsPanel insights={insights} />
      )}
    </div>
  )
}
