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
import { useFilterContext } from "@/contexts/filter-context"
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
  sourceName,
}: {
  insight: Insight
  index: number
  sourceName?: string
}) {
  const { kpiPatches, isRefetching, activeFilters } = useFilterContext()
  const patch = kpiPatches[insight.id]
  const baseValue = insight.data?.value as number | undefined
  const value = patch && !patch.skipped ? patch.value : baseValue
  const changePercent = insight.data?.change_percent as number | undefined
  const currency = insight.data?.is_currency as boolean | undefined
  // Only format as money when the file said which currency it is; otherwise a
  // plain number, rather than showing e.g. UK £m figures as US dollars.
  const currencyCode = insight.data?.currency as string | undefined
  const percent = insight.data?.is_percent as boolean | undefined
  const Icon = getKpiIcon(insight.title)

  const direction =
    changePercent !== undefined
      ? changePercent > 0
        ? "up"
        : changePercent < 0
        ? "down"
        : "neutral"
      : "neutral"

  // Intl defaults to three fraction digits, so an average variance rendered as
  // "-4.414" on a card whose whole job is the headline number.
  const numberFormat: Intl.NumberFormatOptions = { maximumFractionDigits: 2 }
  const unit = insight.data?.unit === "million" ? " million" : ""
  const formattedValue =
    value !== undefined && value !== null
      ? currency
        ? currencyCode
          ? formatCurrency(value, currencyCode)
          : formatNumber(value, numberFormat)
        : percent
        ? `${formatNumber(value, numberFormat)}%`
        : formatNumber(value, numberFormat)
      : "—"
  const displayedValue = value !== undefined && value !== null ? `${formattedValue}${unit}` : formattedValue

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06, duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      className={cn(
        "zephyr-card relative flex flex-col gap-4 overflow-hidden p-5 transition-all hover:-translate-y-0.5 hover:shadow-lg dark:border-zinc-800 dark:bg-zinc-900/60",
        isRefetching && "opacity-60"
      )}
    >
      <div className={cn("absolute inset-x-0 top-0 h-1", ["bg-violet-500", "bg-teal-500", "bg-orange-400", "bg-fuchsia-500"][index % 4])} />
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
          {insight.title}
        </p>
        <div className={cn("flex h-10 w-10 items-center justify-center rounded-xl", ["bg-violet-100 text-violet-700", "bg-teal-100 text-teal-700", "bg-orange-100 text-orange-700", "bg-fuchsia-100 text-fuchsia-700"][index % 4])}>
          <Icon className="h-4.5 w-4.5" />
        </div>
      </div>

      <div className="space-y-1">
        <p className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
          {displayedValue}
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
      {Boolean(insight.data?.column) && (
        <details className="border-t border-zinc-100 pt-3 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
          <summary className="cursor-pointer font-medium text-blue-600 dark:text-blue-400">How calculated</summary>
          {sourceName && <p className="mt-2">Source: {sourceName}</p>}
          <p className="mt-1">
            {percent ? "Percentage of records with a positive value in " :
              insight.data.weighted_by ? "Weighted average of " :
              insight.data.is_total ? "Sum of " : "Average of "}
            {String(insight.data.column)}
            {insight.data.weighted_by ? `, weighted by ${String(insight.data.weighted_by)}` : ""}.
          </p>
          <p className="mt-1">{activeFilters.length > 0
            ? `Applied filters: ${activeFilters.map((filter) => `${filter.display_label} ${filter.op === "date_between" ? `${filter.values[0]} to ${filter.values[1]}` : filter.values.join(", ")}`).join("; ")}.`
            : "All analysed records; no dashboard filters applied."}</p>
        </details>
      )}
    </motion.div>
  )
}

interface KpiGridProps {
  insights: Insight[]
  sourceName?: string
}

export function KpiGrid({ insights, sourceName }: KpiGridProps) {
  const kpiInsights = insights
    .filter((i) => i.type === "summary")
    .slice(0, 8)

  if (kpiInsights.length === 0) return null

  return (
    <section>
      <p className="zephyr-kicker mb-1">At a glance</p>
      <h2 className="mb-4 text-xl font-bold text-[#28203f] dark:text-white">
        Key Metrics
      </h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {kpiInsights.map((insight, i) => (
          <KpiCard key={insight.id} insight={insight} index={i} sourceName={sourceName} />
        ))}
      </div>
    </section>
  )
}
