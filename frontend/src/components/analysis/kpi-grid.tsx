"use client"

import { motion } from "framer-motion"
import {
  TrendingUp,
  TrendingDown,
  Minus,
  DollarSign,
  Users,
  ShoppingCart,
  Percent,
  Activity,
} from "lucide-react"
import { cn, formatNumber, formatCurrency } from "@/lib/utils"
import type { Insight } from "@/types"

const ICON_MAP: Record<string, React.ElementType> = {
  revenue: DollarSign,
  profit: TrendingUp,
  orders: ShoppingCart,
  customers: Users,
  margin: Percent,
  conversion: Percent,
  growth: TrendingUp,
  churn: Activity,
}

function getKpiIcon(title: string): React.ElementType {
  const key = title.toLowerCase()
  for (const [k, Icon] of Object.entries(ICON_MAP)) {
    if (key.includes(k)) return Icon
  }
  return Activity
}

function KpiCard({
  insight,
  index,
}: {
  insight: Insight
  index: number
}) {
  const value = insight.data?.value as number | undefined
  const changePercent = insight.data?.change_percent as number | undefined
  const currency = insight.data?.is_currency as boolean | undefined
  const Icon = getKpiIcon(insight.title)

  const direction =
    changePercent !== undefined
      ? changePercent > 0
        ? "up"
        : changePercent < 0
        ? "down"
        : "neutral"
      : "neutral"

  const formattedValue =
    value !== undefined
      ? currency
        ? formatCurrency(value)
        : formatNumber(value)
      : "—"

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06, duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      className="flex flex-col gap-4 rounded-2xl border bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/60"
    >
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
          {insight.title}
        </p>
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-50 dark:bg-blue-900/30">
          <Icon className="h-4.5 w-4.5 text-blue-600 dark:text-blue-400" />
        </div>
      </div>

      <div className="space-y-1">
        <p className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
          {formattedValue}
        </p>
        {changePercent !== undefined && (
          <div
            className={cn(
              "flex items-center gap-1 text-sm font-medium",
              direction === "up"
                ? "text-emerald-600 dark:text-emerald-400"
                : direction === "down"
                ? "text-red-500 dark:text-red-400"
                : "text-zinc-400"
            )}
          >
            {direction === "up" ? (
              <TrendingUp className="h-3.5 w-3.5" />
            ) : direction === "down" ? (
              <TrendingDown className="h-3.5 w-3.5" />
            ) : (
              <Minus className="h-3.5 w-3.5" />
            )}
            <span>
              {Math.abs(changePercent).toFixed(1)}%
              <span className="ml-1 font-normal text-zinc-400">vs last period</span>
            </span>
          </div>
        )}
      </div>
    </motion.div>
  )
}

interface KpiGridProps {
  insights: Insight[]
}

export function KpiGrid({ insights }: KpiGridProps) {
  const kpiInsights = insights
    .filter((i) => i.type === "summary")
    .slice(0, 8)

  if (kpiInsights.length === 0) return null

  return (
    <section>
      <h2 className="mb-4 text-base font-semibold text-zinc-900 dark:text-white">
        Key Metrics
      </h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {kpiInsights.map((insight, i) => (
          <KpiCard key={insight.id} insight={insight} index={i} />
        ))}
      </div>
    </section>
  )
}
