"use client"

import Link from "next/link"
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Clock3,
  FileSpreadsheet,
  Loader2,
  Upload,
} from "lucide-react"
import type { LucideIcon } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { EmptyDashboard } from "@/components/dashboard/empty-dashboard"
import { useAnalyses } from "@/hooks/use-analyses"
import { formatNumber, formatRelativeTime } from "@/lib/utils"
import type { AnalysisListItem, AnalysisStatus } from "@/types"

const statusMeta: Record<
  AnalysisStatus,
  {
    label: string
    variant: "secondary" | "success" | "warning" | "destructive"
    icon: LucideIcon
  }
> = {
  pending: { label: "Queued", variant: "secondary", icon: Clock3 },
  processing: { label: "Processing", variant: "warning", icon: Loader2 },
  completed: { label: "Ready", variant: "success", icon: CheckCircle2 },
  failed: { label: "Failed", variant: "destructive", icon: AlertTriangle },
}

function MetricTile({
  label,
  value,
  icon: Icon,
  tone,
}: {
  label: string
  value: string
  icon: LucideIcon
  tone: "blue" | "emerald" | "amber" | "zinc"
}) {
  const tones = {
    blue: "bg-blue-50 text-blue-600 dark:bg-blue-950/40 dark:text-blue-300",
    emerald:
      "bg-emerald-50 text-emerald-600 dark:bg-emerald-950/40 dark:text-emerald-300",
    amber:
      "bg-amber-50 text-amber-600 dark:bg-amber-950/40 dark:text-amber-300",
    zinc: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300",
  }

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900/60">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">{label}</p>
          <p className="mt-2 text-2xl font-semibold tracking-tight text-zinc-950 dark:text-white">
            {value}
          </p>
        </div>
        <div
          className={`flex h-10 w-10 items-center justify-center rounded-lg ${tones[tone]}`}
        >
          <Icon className="h-5 w-5" />
        </div>
      </div>
    </div>
  )
}

function RecentAnalysisRow({ analysis }: { analysis: AnalysisListItem }) {
  const meta = statusMeta[analysis.status]
  const StatusIcon = meta.icon
  const content = (
    <div className="flex items-center justify-between gap-4 rounded-lg border border-zinc-200 bg-white px-4 py-3 transition-colors hover:border-zinc-300 dark:border-zinc-800 dark:bg-zinc-900/60 dark:hover:border-zinc-700">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <p className="truncate text-sm font-medium text-zinc-950 dark:text-white">
            {analysis.name}
          </p>
          <Badge variant={meta.variant} className="shrink-0 text-[11px]">
            <StatusIcon
              className={`mr-1 h-3 w-3 ${
                analysis.status === "processing" ? "animate-spin" : ""
              }`}
            />
            {meta.label}
          </Badge>
        </div>
        <p className="mt-1 text-xs text-zinc-500">
          {formatNumber(analysis.row_count ?? 0)} rows -{" "}
          {analysis.column_count ?? 0} columns -{" "}
          {formatRelativeTime(analysis.created_at)}
        </p>
      </div>
      {analysis.status === "completed" ? (
        <ArrowRight className="h-4 w-4 shrink-0 text-zinc-400" />
      ) : null}
    </div>
  )

  if (analysis.status !== "completed") return content

  return <Link href={`/analysis/${analysis.id}`}>{content}</Link>
}

export function DashboardOverview() {
  const { data, isLoading } = useAnalyses({ limit: 8 })
  const analyses = data?.items ?? []

  if (!analyses.length && !isLoading) {
    return <EmptyDashboard />
  }

  const total = data?.total ?? analyses.length
  const completed = analyses.filter(
    (analysis) => analysis.status === "completed"
  ).length
  const active = analyses.filter((analysis) =>
    ["pending", "processing"].includes(analysis.status)
  ).length
  const rows = analyses.reduce(
    (sum, analysis) => sum + (analysis.row_count || 0),
    0
  )

  return (
    <div className="space-y-8">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricTile
          label="Analyses"
          value={formatNumber(total)}
          icon={BarChart3}
          tone="blue"
        />
        <MetricTile
          label="Ready"
          value={formatNumber(completed)}
          icon={CheckCircle2}
          tone="emerald"
        />
        <MetricTile
          label="In progress"
          value={formatNumber(active)}
          icon={Clock3}
          tone="amber"
        />
        <MetricTile
          label="Rows indexed"
          value={formatNumber(rows)}
          icon={FileSpreadsheet}
          tone="zinc"
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1fr_320px]">
        <section className="space-y-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold text-zinc-950 dark:text-white">
                Recent analyses
              </h2>
              <p className="text-sm text-zinc-500">
                Latest uploaded datasets and analysis runs.
              </p>
            </div>
            <Button asChild variant="outline" size="sm">
              <Link href="/analyses">
                View all
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
          </div>

          <div className="space-y-3">
            {isLoading
              ? Array.from({ length: 4 }).map((_, index) => (
                  <div
                    key={index}
                    className="h-[70px] animate-pulse rounded-lg border border-zinc-200 bg-zinc-100 dark:border-zinc-800 dark:bg-zinc-900"
                  />
                ))
              : analyses.slice(0, 5).map((analysis) => (
                  <RecentAnalysisRow key={analysis.id} analysis={analysis} />
                ))}
          </div>
        </section>

        <aside className="rounded-lg border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900/60">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 text-blue-600 dark:bg-blue-950/40 dark:text-blue-300">
            <Upload className="h-5 w-5" />
          </div>
          <h2 className="mt-4 text-lg font-semibold text-zinc-950 dark:text-white">
            Start a new analysis
          </h2>
          <p className="mt-2 text-sm text-zinc-500">
            Upload one workbook or queue several files before running analysis.
          </p>
          <Button asChild className="mt-5 w-full">
            <Link href="/upload">
              <Upload className="h-4 w-4" />
              New analysis
            </Link>
          </Button>
        </aside>
      </div>
    </div>
  )
}
