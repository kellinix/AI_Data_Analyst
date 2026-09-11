"use client"

import type { ReactNode } from "react"
import { motion } from "framer-motion"
import { toast } from "sonner"
import {
  ArrowUpRight,
  AlertCircle,
  Target,
  Clock,
  ThumbsDown,
  ThumbsUp,
  User,
  Zap,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { useRecommendationFeedback } from "@/hooks/use-analyses"
import { cn, formatCurrency } from "@/lib/utils"
import type { Insight, RecommendationFeedbackVerdict } from "@/types"

const priorityConfig = {
  critical: {
    variant: "destructive" as const,
    label: "Critical",
    dot: "bg-red-500",
  },
  high: {
    variant: "warning" as const,
    label: "High",
    dot: "bg-amber-500",
  },
  medium: {
    variant: "secondary" as const,
    label: "Medium",
    dot: "bg-blue-500",
  },
  low: {
    variant: "secondary" as const,
    label: "Low",
    dot: "bg-zinc-400",
  },
}

function FeedbackButton({
  label,
  active,
  disabled,
  onClick,
  children,
}: {
  label: string
  active: boolean
  disabled: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      aria-label={label}
      aria-pressed={active}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "rounded-md p-1.5 text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-700 disabled:opacity-50 dark:hover:bg-zinc-800 dark:hover:text-zinc-200",
        active &&
          "bg-orange-50 text-orange-600 hover:bg-orange-50 hover:text-orange-600 dark:bg-orange-950/40 dark:text-orange-400"
      )}
    >
      {children}
    </button>
  )
}

/** Owner-only verdict control. Each verdict is logged with the confidence the
 * recommendation was shown with, so confidence can be checked against real use. */
function RecommendationFeedback({
  analysisId,
  insight,
}: {
  analysisId: string
  insight: Insight
}) {
  const feedback = useRecommendationFeedback(analysisId)
  const current = insight.user_feedback ?? null

  function choose(verdict: RecommendationFeedbackVerdict) {
    feedback.mutate(
      { insightId: insight.id, verdict: current === verdict ? null : verdict },
      { onError: () => toast.error("Couldn't save your feedback") }
    )
  }

  return (
    <div className="mt-4 flex items-center justify-between border-t border-zinc-100 pt-3 dark:border-zinc-800">
      <p className="text-xs text-zinc-500 dark:text-zinc-400">
        {current ? "Thanks for the feedback" : "Was this useful?"}
      </p>
      <div className="flex gap-1" role="group" aria-label="Rate this recommendation">
        <FeedbackButton
          label="Useful"
          active={current === "helpful"}
          disabled={feedback.isPending}
          onClick={() => choose("helpful")}
        >
          <ThumbsUp className="h-3.5 w-3.5" />
        </FeedbackButton>
        <FeedbackButton
          label="Not useful"
          active={current === "not_helpful"}
          disabled={feedback.isPending}
          onClick={() => choose("not_helpful")}
        >
          <ThumbsDown className="h-3.5 w-3.5" />
        </FeedbackButton>
      </div>
    </div>
  )
}

function RecommendationCard({
  insight,
  index,
  analysisId,
}: {
  insight: Insight
  index: number
  analysisId?: string
}) {
  const config = priorityConfig[insight.importance]
  const data = insight.data as {
    problem?: string
    evidence?: string
    expected_impact?: string
    financial_opportunity?: number
    show_financial_opportunity?: boolean
    difficulty?: string
    owner?: string
    estimated_completion?: string
  }
  const financialOpportunity =
    typeof data.financial_opportunity === "number"
      ? data.financial_opportunity
      : null
  const showOpportunity =
    data.show_financial_opportunity === true &&
    financialOpportunity !== null &&
    financialOpportunity > 0

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.08, duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      className="rounded-2xl border bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/60"
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className={cn("mt-0.5 h-2 w-2 flex-shrink-0 rounded-full", config.dot)} />
          <h3 className="text-sm font-semibold text-zinc-900 dark:text-white">
            {insight.title}
          </h3>
        </div>
        <Badge variant={config.variant} className="flex-shrink-0 text-[11px]">
          {config.label}
        </Badge>
      </div>

      {/* Description */}
      <p className="mt-3 text-sm leading-relaxed text-zinc-600 dark:text-zinc-300">
        {insight.description}
      </p>

      {/* Evidence */}
      {data.evidence && (
        <div className="mt-3 rounded-lg bg-zinc-50 p-3 dark:bg-zinc-800/50">
          <p className="flex items-center gap-1.5 text-xs font-medium text-zinc-500 dark:text-zinc-400">
            <AlertCircle className="h-3.5 w-3.5" />
            Evidence
          </p>
          <p className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">
            {data.evidence}
          </p>
        </div>
      )}

      {/* Metadata grid */}
      <div className="mt-4 grid grid-cols-2 gap-3">
        {showOpportunity && (
          <div className="flex items-start gap-2">
            <ArrowUpRight className="mt-0.5 h-4 w-4 flex-shrink-0 text-emerald-500" />
            <div>
              <p className="text-[10px] font-medium uppercase tracking-wide text-zinc-400">
                Opportunity
              </p>
              <p className="text-sm font-semibold text-emerald-600 dark:text-emerald-400">
                +{formatCurrency(financialOpportunity ?? 0)}
              </p>
            </div>
          </div>
        )}
        {data.difficulty && (
          <div className="flex items-start gap-2">
            <Zap className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-500" />
            <div>
              <p className="text-[10px] font-medium uppercase tracking-wide text-zinc-400">
                Difficulty
              </p>
              <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                {data.difficulty}
              </p>
            </div>
          </div>
        )}
        {data.owner && (
          <div className="flex items-start gap-2">
            <User className="mt-0.5 h-4 w-4 flex-shrink-0 text-blue-500" />
            <div>
              <p className="text-[10px] font-medium uppercase tracking-wide text-zinc-400">
                Owner
              </p>
              <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                {data.owner}
              </p>
            </div>
          </div>
        )}
        {data.estimated_completion && (
          <div className="flex items-start gap-2">
            <Clock className="mt-0.5 h-4 w-4 flex-shrink-0 text-violet-500" />
            <div>
              <p className="text-[10px] font-medium uppercase tracking-wide text-zinc-400">
                Timeline
              </p>
              <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                {data.estimated_completion}
              </p>
            </div>
          </div>
        )}
      </div>

      {analysisId && <RecommendationFeedback analysisId={analysisId} insight={insight} />}
    </motion.div>
  )
}

interface RecommendationsPanelProps {
  insights: Insight[]
  /** Enables owner feedback on each card; omit on shared/public views. */
  analysisId?: string
}

function normalizeRecommendationKey(insight: Insight): string {
  const title = insight.title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
  const data = insight.data as Record<string, unknown>
  const evidence =
    typeof data.evidence === "string"
      ? data.evidence
          .toLowerCase()
          .replace(/\d[\d,.\s]*/g, "#")
          .replace(/[^a-z0-9#]+/g, " ")
          .trim()
      : ""

  if (title.includes("high volume") || title.includes("concentration")) {
    return `volume:${evidence}`
  }

  return `${title}:${evidence}`
}

function dedupeRecommendations(recommendations: Insight[]): Insight[] {
  const seen = new Set<string>()
  const deduped: Insight[] = []

  for (const recommendation of recommendations) {
    const key = normalizeRecommendationKey(recommendation)
    if (seen.has(key)) continue
    seen.add(key)
    deduped.push(recommendation)
  }

  return deduped
}

export function RecommendationsPanel({ insights, analysisId }: RecommendationsPanelProps) {
  const recommendations = dedupeRecommendations(
    insights.filter((i) => i.type === "recommendation")
  )
    .sort((a, b) => {
      const order = { critical: 0, high: 1, medium: 2, low: 3 }
      return order[a.importance] - order[b.importance]
    })
    .slice(0, 4)

  if (recommendations.length === 0) return null

  return (
    <section>
      <div className="mb-4 flex items-center gap-2">
        <Target className="h-5 w-5 text-orange-500" />
        <h2 className="text-base font-semibold text-zinc-900 dark:text-white">
          Recommended Actions
        </h2>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {recommendations.map((rec, i) => (
          <RecommendationCard key={rec.id} insight={rec} index={i} analysisId={analysisId} />
        ))}
      </div>
    </section>
  )
}
