"use client"

import { useState } from "react"
import { motion } from "framer-motion"
import { TrendingUp, AlertTriangle, Lightbulb, Activity } from "lucide-react"
import { cn } from "@/lib/utils"
import { Badge } from "@/components/ui/badge"
import type { Insight } from "@/types"

const typeConfig = {
  trend: {
    icon: TrendingUp,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-50 dark:bg-blue-900/30",
  },
  anomaly: {
    icon: AlertTriangle,
    color: "text-amber-600 dark:text-amber-400",
    bg: "bg-amber-50 dark:bg-amber-900/30",
  },
  correlation: {
    icon: Activity,
    color: "text-violet-600 dark:text-violet-400",
    bg: "bg-violet-50 dark:bg-violet-900/30",
  },
  distribution: {
    icon: Activity,
    color: "text-zinc-600 dark:text-zinc-400",
    bg: "bg-zinc-100 dark:bg-zinc-800",
  },
  summary: {
    icon: Activity,
    color: "text-emerald-600 dark:text-emerald-400",
    bg: "bg-emerald-50 dark:bg-emerald-900/30",
  },
  forecast: {
    icon: TrendingUp,
    color: "text-indigo-600 dark:text-indigo-400",
    bg: "bg-indigo-50 dark:bg-indigo-900/30",
  },
  recommendation: {
    icon: Lightbulb,
    color: "text-orange-600 dark:text-orange-400",
    bg: "bg-orange-50 dark:bg-orange-900/30",
  },
}

const importanceVariant = {
  low: "secondary" as const,
  medium: "warning" as const,
  high: "warning" as const,
  critical: "destructive" as const,
}

function titleCase(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1)
}

function signalLabel(confidence: number): string {
  if (confidence >= 0.85) return "Strong signal"
  if (confidence >= 0.65) return "Good signal"
  return "Worth a look"
}

function InsightCard({ insight, index }: { insight: Insight; index: number }) {
  const [expanded, setExpanded] = useState(false)
  const config = typeConfig[insight.type] ?? typeConfig.trend
  const Icon = config.icon

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05, duration: 0.35 }}
      className="rounded-xl border bg-white p-5 transition-all hover:shadow-sm dark:border-zinc-800 dark:bg-zinc-900/60"
    >
      <div className="flex items-start gap-3">
        <div className={cn("flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg", config.bg)}>
          <Icon className={cn("h-4 w-4", config.color)} />
        </div>
        <div className="flex-1 space-y-1.5">
          <div className="flex items-start justify-between gap-3">
            <h3 className="text-sm font-semibold text-zinc-900 dark:text-white">
              {insight.title}
            </h3>
            <Badge variant={importanceVariant[insight.importance]} className="flex-shrink-0 text-[10px]">
              {titleCase(insight.importance)}
            </Badge>
          </div>
          <p className={cn("text-sm leading-relaxed text-zinc-600 dark:text-zinc-300", !expanded && "line-clamp-2")}>
            {insight.description}
          </p>
          {insight.description.length > 120 && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="text-xs font-medium text-blue-600 hover:text-blue-500 dark:text-blue-400"
            >
              {expanded ? "Show less" : "Read more"}
            </button>
          )}
          {/* Signal strength */}
          <div className="flex items-center gap-2 pt-1">
            <div className="h-1 w-24 overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
              <div
                className="h-full rounded-full bg-blue-500 transition-all"
                style={{ width: `${insight.confidence * 100}%` }}
              />
            </div>
            <span className="text-[11px] text-zinc-400">
              {signalLabel(insight.confidence)}
            </span>
          </div>
        </div>
      </div>
    </motion.div>
  )
}

interface InsightsPanelProps {
  insights: Insight[]
}

function normalizeInsightKey(insight: Insight): string {
  const data = insight.data as Record<string, unknown>
  const column = typeof data.column === "string" ? data.column : ""
  if (insight.type === "anomaly" && column) {
    return `${insight.type}:${column}`
  }

  return `${insight.type}:${insight.title}`
    .toLowerCase()
    .replace(/\d[\d,.\s]*/g, "#")
    .replace(/\s+/g, " ")
    .trim()
}

function dedupeInsights(insights: Insight[]): Insight[] {
  const seen = new Set<string>()
  const deduped: Insight[] = []

  for (const insight of insights) {
    const key = normalizeInsightKey(insight)
    if (seen.has(key)) continue
    seen.add(key)
    deduped.push(insight)
  }

  return deduped
}

export function InsightsPanel({ insights }: InsightsPanelProps) {
  const displayInsights = dedupeInsights(
    insights.filter((i) => i.type !== "summary" && i.type !== "recommendation")
  )
    .sort((a, b) => {
      const order = { critical: 0, high: 1, medium: 2, low: 3 }
      return order[a.importance] - order[b.importance]
    })
    .slice(0, 6)

  if (displayInsights.length === 0) return null

  return (
    <section>
      <h2 className="mb-4 text-base font-semibold text-zinc-900 dark:text-white">
        AI Insights
      </h2>
      <div className="grid gap-3 md:grid-cols-2">
        {displayInsights.map((insight, i) => (
          <InsightCard key={insight.id} insight={insight} index={i} />
        ))}
      </div>
    </section>
  )
}
