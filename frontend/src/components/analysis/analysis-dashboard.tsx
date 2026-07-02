"use client"

import { Component, type ReactNode, useEffect, useState } from "react"
import { motion } from "framer-motion"
import { notFound } from "next/navigation"
import { useQueryClient } from "@tanstack/react-query"
import { analysisKeys, useAnalysis, useAnalysisStatus } from "@/hooks/use-analyses"
import { KpiGrid } from "@/components/analysis/kpi-grid"
import { ExecutiveSummary } from "@/components/analysis/executive-summary"
import { InsightsPanel } from "@/components/analysis/insights-panel"
import { ChartsGrid } from "@/components/analysis/charts-grid"
import { RecommendationsPanel } from "@/components/analysis/recommendations-panel"
import { DataQualityPanel } from "@/components/analysis/data-quality-panel"
import { ChatPanel } from "@/components/chat/chat-panel"
import { AnalysisHeader } from "@/components/analysis/analysis-header"
import { ProcessingBanner } from "@/components/analysis/processing-banner"
import { AnalysisDashboardSkeleton } from "@/components/analysis/analysis-dashboard-skeleton"
import { Button } from "@/components/ui/button"
import { MessageSquare } from "lucide-react"

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
  const { data: analysis, isLoading, error } = useAnalysis(id)
  const { data: status } = useAnalysisStatus(
    id,
    analysis?.status !== "completed" && analysis?.status !== "failed"
  )

  useEffect(() => {
    if (status?.status === "completed" || status?.status === "failed") {
      queryClient.invalidateQueries({ queryKey: analysisKeys.detail(id) })
    }
  }, [id, queryClient, status?.status])

  if (isLoading) return <AnalysisDashboardSkeleton />
  if (error || !analysis) return notFound()

  const shouldUsePolledStatus =
    analysis.status === "pending" || analysis.status === "processing"
  const currentStatus = shouldUsePolledStatus
    ? status?.status ?? analysis.status
    : analysis.status
  const currentProgress = shouldUsePolledStatus ? status?.progress ?? 0 : 100
  const isProcessing = currentStatus === "processing" || currentStatus === "pending"
  const insights = Array.isArray(analysis.insights) ? analysis.insights : []
  const charts = Array.isArray(analysis.charts) ? analysis.charts : []
  const hasGeneratedContent = Boolean(analysis.summary) || insights.length > 0 || charts.length > 0

  return (
    <div className="flex h-full">
      {/* Main content */}
      <div className="flex flex-1 flex-col overflow-y-auto">
        {/* Processing banner */}
        {isProcessing && (
          <ProcessingBanner
            progress={currentProgress}
          />
        )}

        <div className="flex flex-col gap-8 p-8">
          {/* Analysis header */}
          <AnalysisHeader analysis={analysis} status={currentStatus} />

          {isProcessing ? (
            <AnalysisDashboardSkeleton />
          ) : (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.4 }}
              className="flex flex-col gap-8"
            >
              {!hasGeneratedContent && (
                <section className="rounded-lg border border-zinc-200 bg-zinc-50 p-5 text-sm text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900/50 dark:text-zinc-300">
                  This analysis is marked ready, but no summary, charts, or insights were returned by the API.
                </section>
              )}

              {/* Executive summary */}
              {analysis.summary && (
                <SectionErrorBoundary title="Executive summary">
                  <ExecutiveSummary summary={analysis.summary} />
                </SectionErrorBoundary>
              )}

              {/* KPI grid */}
              {insights.length > 0 && (
                <SectionErrorBoundary title="Key metrics">
                  <KpiGrid insights={insights} />
                </SectionErrorBoundary>
              )}

              {/* Charts */}
              {charts.length > 0 && (
                <SectionErrorBoundary title="Charts">
                  <ChartsGrid charts={charts} />
                </SectionErrorBoundary>
              )}

              {/* Insights */}
              {insights.length > 0 && (
                <SectionErrorBoundary title="AI insights">
                  <InsightsPanel insights={insights} />
                </SectionErrorBoundary>
              )}

              {/* Recommendations */}
              {insights.some((i) => i.type === "recommendation") && (
                <SectionErrorBoundary title="Recommendations">
                  <RecommendationsPanel insights={insights} />
                </SectionErrorBoundary>
              )}

              {/* Data quality */}
              {analysis.metadata && (
                <SectionErrorBoundary title="Data quality">
                  <DataQualityPanel metadata={analysis.metadata} />
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
          onClose={() => setIsChatOpen(false)}
        />
      )}

      {/* Chat toggle FAB */}
      {!isChatOpen && !isProcessing && (
        <motion.div
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ delay: 1, type: "spring", stiffness: 260, damping: 20 }}
          className="fixed bottom-6 right-6"
        >
          <Button
            onClick={() => setIsChatOpen(true)}
            size="lg"
            className="h-14 w-14 rounded-2xl bg-blue-600 shadow-lg shadow-blue-600/30 hover:bg-blue-500"
          >
            <MessageSquare className="h-6 w-6" />
          </Button>
        </motion.div>
      )}
    </div>
  )
}
