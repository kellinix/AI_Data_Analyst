"use client"

import { Component, type ReactNode, useEffect, useState } from "react"
import { motion } from "framer-motion"
import { notFound } from "next/navigation"
import { useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import {
  analysisKeys,
  useAnalysis,
  useAnalysisStatus,
  useRerunAnalysis,
} from "@/hooks/use-analyses"
import { KpiGrid } from "@/components/analysis/kpi-grid"
import { MetricDefinitionsPanel } from "@/components/analysis/metric-definitions-panel"
import { ExecutiveSummary } from "@/components/analysis/executive-summary"
import { InsightsPanel } from "@/components/analysis/insights-panel"
import { ChartsGrid } from "@/components/analysis/charts-grid"
import { SlicerBar } from "@/components/analysis/slicer-bar"
import { RecommendationsPanel } from "@/components/analysis/recommendations-panel"
import { ComparisonPanel } from "@/components/analysis/comparison-panel"
import { DataQualityPanel } from "@/components/analysis/data-quality-panel"
import { ChatPanel } from "@/components/chat/chat-panel"
import { AnalysisHeader } from "@/components/analysis/analysis-header"
import { ProcessingBanner } from "@/components/analysis/processing-banner"
import { AnalysisDashboardSkeleton } from "@/components/analysis/analysis-dashboard-skeleton"
import { Button } from "@/components/ui/button"
import { FilterProvider } from "@/contexts/filter-context"
import type { FilterableColumn } from "@/types"
import { DashboardProvider } from "@/contexts/dashboard-context"
import { AlertTriangle, MessageSquare, RefreshCw } from "lucide-react"

const EMPTY_FILTERABLE_COLUMNS: FilterableColumn[] = []

function isNotFoundError(error: unknown): boolean {
  const maybeAxiosError = error as { response?: { status?: number } } | null
  return maybeAxiosError?.response?.status === 404
}

interface AnalysisDashboardProps {
  id: string
}

class SectionErrorBoundary extends Component<
  { title: string; children: ReactNode },
  { hasError: boolean }
> {
  state = { hasError: false }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error: unknown) {
    console.error(`${this.props.title} failed to render`, error)
  }

  render() {
    if (this.state.hasError) {
      return (
        <section className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">
          {this.props.title} could not be displayed. The analysis data was generated, but this section hit a rendering error.
        </section>
      )
    }

    return this.props.children
  }
}

export function AnalysisDashboard({ id }: AnalysisDashboardProps) {
  const [isChatOpen, setIsChatOpen] = useState(false)
  const queryClient = useQueryClient()
  const { data: analysis, isLoading, error, refetch } = useAnalysis(id)
  const { data: status } = useAnalysisStatus(
    id,
    analysis?.status !== "completed" && analysis?.status !== "failed"
  )
  const rerunAnalysis = useRerunAnalysis()

  useEffect(() => {
    if (status?.status === "completed" || status?.status === "failed") {
      queryClient.invalidateQueries({ queryKey: analysisKeys.detail(id) })
    }
  }, [id, queryClient, status?.status])

  if (isLoading) return <AnalysisDashboardSkeleton />
  if (error && isNotFoundError(error)) return notFound()
  if (error || !analysis) {
    return (
      <div className="flex min-h-[420px] flex-col items-center justify-center gap-4 p-8 text-center">
        <AlertTriangle className="h-10 w-10 text-amber-500" />
        <div className="space-y-1">
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
            Couldn&apos;t load this analysis
          </h2>
          <p className="max-w-sm text-sm text-zinc-500">
            Something went wrong while fetching this page. Your analysis is safe — try again in a moment.
          </p>
        </div>
        <Button onClick={() => refetch()} variant="outline">
          <RefreshCw className="mr-2 h-4 w-4" />
          Try again
        </Button>
      </div>
    )
  }

  const shouldUsePolledStatus =
    analysis.status === "pending" || analysis.status === "processing"
  const currentStatus = shouldUsePolledStatus
    ? status?.status ?? analysis.status
    : analysis.status
  const currentProgress = shouldUsePolledStatus ? status?.progress ?? 0 : 100
  const isProcessing = currentStatus === "processing" || currentStatus === "pending"
  const isFailed = currentStatus === "failed"
  const insights = Array.isArray(analysis.insights) ? analysis.insights : []
  const charts = Array.isArray(analysis.charts) ? analysis.charts : []
  const filterableColumns = analysis.filterable_columns ?? EMPTY_FILTERABLE_COLUMNS
  const hasGeneratedContent = Boolean(analysis.summary) || insights.length > 0 || charts.length > 0
  const aiGeneration = analysis.metadata?.ai_generation as { status?: string } | null | undefined
  const aiFellBack = !isProcessing && aiGeneration?.status === "fallback"
  const recordContext = analysis.metadata?.record_context as { description?: string } | undefined

  async function handleRetry() {
    try {
      await rerunAnalysis.mutateAsync(id)
      toast.success("Analysis restarted")
    } catch (retryError) {
      console.error("Retrying analysis failed", retryError)
      toast.error("Couldn't restart the analysis")
    }
  }

  return (
    <DashboardProvider analysisId={id} enabled={!isProcessing && !isFailed}>
    <FilterProvider analysisId={id} filterableColumns={filterableColumns}>
    <div className="flex h-full">
      {/* Main content */}
      <div className="flex flex-1 flex-col overflow-y-auto">
        {/* Processing banner */}
        {isProcessing && (
          <ProcessingBanner
            progress={currentProgress}
          />
        )}

        <div className="flex flex-col gap-8 p-5 sm:p-8">
          {/* Analysis header */}
          <AnalysisHeader analysis={analysis} status={currentStatus} />
          {recordContext?.description && <section className="rounded-2xl border bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900"><h2 className="font-semibold">What this data is about</h2><p className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">{recordContext.description}</p></section>}

          {isProcessing ? (
            <AnalysisDashboardSkeleton />
          ) : isFailed ? (
            <div className="flex flex-col items-center justify-center gap-4 rounded-lg border border-red-200 bg-red-50 p-10 text-center dark:border-red-900/50 dark:bg-red-950/20">
              <AlertTriangle className="h-10 w-10 text-red-500" />
              <div className="space-y-1">
                <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
                  This analysis couldn&apos;t be completed
                </h2>
                <p className="max-w-md text-sm text-zinc-600 dark:text-zinc-300">
                  {analysis.error_message ||
                    "Something went wrong while analysing this file. This is usually caused by a formatting issue in the file itself."}
                </p>
              </div>
              <Button onClick={handleRetry} disabled={rerunAnalysis.isPending}>
                <RefreshCw className="mr-2 h-4 w-4" />
                Try again
              </Button>
            </div>
          ) : (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.4 }}
              className="flex flex-col gap-8"
            >
              {!hasGeneratedContent && (
                <section className="rounded-lg border border-zinc-200 bg-zinc-50 p-5 text-sm text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900/50 dark:text-zinc-300">
                  This analysis finished, but didn&apos;t produce a summary, charts, or insights. Try re-analysing the file, or check that it has enough data to work with.
                </section>
              )}

              {aiFellBack && (
                <section className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">
                  <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" />
                  <p>
                    The AI service was unavailable for this analysis, so the summary and
                    recommendations below were generated automatically from the statistics.
                    Re-analyse to try the AI narrative again.
                  </p>
                </section>
              )}

              {/* Executive summary */}
              {analysis.summary && (
                <SectionErrorBoundary title="Executive summary">
                  <ExecutiveSummary summary={analysis.summary} analysisEvidence={analysis.metadata?.analysis_evidence} />
                </SectionErrorBoundary>
              )}

              {/* KPI cards and charts use the shared live filter state.
                  Narrative sections remain saved full-dataset snapshots. */}
                {/* KPI grid */}
                {insights.length > 0 && (
                  <SectionErrorBoundary title="Key metrics">
                    <KpiGrid insights={insights} sourceName={analysis.filename} />
                  </SectionErrorBoundary>
                )}

                <SectionErrorBoundary title="Approved metrics">
                  <MetricDefinitionsPanel analysis={analysis} />
                </SectionErrorBoundary>

                {filterableColumns.length > 0 && (
                  <SectionErrorBoundary title="Filters">
                    <SlicerBar filterableColumns={filterableColumns} />
                  </SectionErrorBoundary>
                )}

                {/* Charts */}
                {charts.length > 0 && (
                  <SectionErrorBoundary title="Charts">
                    <ChartsGrid charts={charts} analysisId={id} />
                  </SectionErrorBoundary>
                )}

              <ComparisonPanel analysis={analysis} />

              {/* Insights */}
              {insights.length > 0 && (
                <SectionErrorBoundary title="AI insights">
                  <InsightsPanel insights={insights} analysisId={id} />
                </SectionErrorBoundary>
              )}

              {/* Recommendations */}
              {insights.some((i) => i.type === "recommendation") && (
                <SectionErrorBoundary title="Recommendations">
                  <RecommendationsPanel insights={insights} analysisId={id} />
                </SectionErrorBoundary>
              )}

              {/* Data quality */}
              {analysis.metadata && (
                <SectionErrorBoundary title="Data quality">
                  <DataQualityPanel metadata={analysis.metadata} analysisId={id} />
                </SectionErrorBoundary>
              )}
            </motion.div>
          )}
        </div>
      </div>

      {/* Chat panel */}
      {isChatOpen && (
        <ChatPanel
          analysisId={id}
          charts={charts}
          onClose={() => setIsChatOpen(false)}
        />
      )}

      {/* Chat toggle FAB */}
      {!isChatOpen && !isProcessing && !isFailed && (
        <motion.div
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ delay: 1, type: "spring", stiffness: 260, damping: 20 }}
          className="fixed bottom-6 right-6"
        >
          <Button
            onClick={() => setIsChatOpen(true)}
            size="lg"
            className="h-14 w-14 rounded-2xl bg-gradient-to-br from-violet-600 to-fuchsia-500 shadow-lg shadow-violet-600/30 hover:from-violet-500 hover:to-fuchsia-400"
          >
            <MessageSquare className="h-6 w-6" />
          </Button>
        </motion.div>
      )}
    </div>
    </FilterProvider>
    </DashboardProvider>
  )
}
