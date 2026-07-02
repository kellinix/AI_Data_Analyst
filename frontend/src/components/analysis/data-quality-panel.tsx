"use client"

import { motion } from "framer-motion"
import { CheckCircle2, Database, ShieldAlert, Wrench } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

interface DataQualityIssue {
  type: string
  column?: string | null
  severity: "low" | "medium" | "high" | "critical"
  description: string
  affected_rows?: number
}

interface DataQualityFix {
  id: string
  label: string
  type: string
  safe_to_auto_apply: boolean
}

interface DataQuality {
  score?: number
  issues?: DataQualityIssue[]
  fixes?: DataQualityFix[]
}

interface DataQualityPanelProps {
  metadata: Record<string, unknown>
}

const severityClass = {
  low: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300",
  medium: "bg-amber-50 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300",
  high: "bg-orange-50 text-orange-700 dark:bg-orange-950/50 dark:text-orange-300",
  critical: "bg-red-50 text-red-700 dark:bg-red-950/50 dark:text-red-300",
}

export function DataQualityPanel({ metadata }: DataQualityPanelProps) {
  const quality = metadata.data_quality as DataQuality | undefined
  if (!quality) return null

  const score = quality.score ?? 0
  const issues = quality.issues ?? []
  const fixes = quality.fixes ?? []
  const healthy = score >= 90 && issues.length === 0

  return (
    <section>
      <div className="mb-4 flex items-center gap-2">
        <Database className="h-5 w-5 text-teal-600" />
        <h2 className="text-base font-semibold text-zinc-900 dark:text-white">
          Data Quality
        </h2>
      </div>

      <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-2xl border bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/60"
        >
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
              Quality score
            </p>
            {healthy ? (
              <CheckCircle2 className="h-5 w-5 text-emerald-500" />
            ) : (
              <ShieldAlert className="h-5 w-5 text-amber-500" />
            )}
          </div>
          <div className="mt-5 flex items-end gap-2">
            <span className="text-4xl font-bold tracking-tight text-zinc-900 dark:text-white">
              {score}
            </span>
            <span className="pb-1 text-sm font-medium text-zinc-400">/100</span>
          </div>
          <div className="mt-4 h-2 overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
            <div
              className={cn(
                "h-full rounded-full",
                score >= 90 ? "bg-emerald-500" : score >= 75 ? "bg-amber-500" : "bg-red-500"
              )}
              style={{ width: `${score}%` }}
            />
          </div>
          <p className="mt-3 text-xs leading-relaxed text-zinc-500 dark:text-zinc-400">
            {healthy
              ? "No major quality issues detected."
              : `${issues.length} issue${issues.length === 1 ? "" : "s"} detected before AI reasoning.`}
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="rounded-2xl border bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/60"
        >
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-zinc-900 dark:text-white">
              Checks
            </h3>
            {fixes.length > 0 && (
              <div className="flex items-center gap-1.5 text-xs font-medium text-blue-600 dark:text-blue-400">
                <Wrench className="h-3.5 w-3.5" />
                {fixes.length} suggested fix{fixes.length === 1 ? "" : "es"}
              </div>
            )}
          </div>

          <div className="mt-4 space-y-3">
            {issues.slice(0, 5).map((issue, index) => (
              <div
                key={`${issue.type}-${issue.column ?? "dataset"}-${index}`}
                className="flex items-start justify-between gap-4 rounded-xl bg-zinc-50 p-3 dark:bg-zinc-800/50"
              >
                <div>
                  <p className="text-sm font-medium text-zinc-800 dark:text-zinc-100">
                    {issue.column ?? "Dataset"}
                  </p>
                  <p className="mt-0.5 text-xs leading-relaxed text-zinc-500 dark:text-zinc-400">
                    {issue.description}
                  </p>
                </div>
                <Badge className={cn("border-0 text-[10px]", severityClass[issue.severity])}>
                  {issue.severity}
                </Badge>
              </div>
            ))}

            {issues.length === 0 && (
              <div className="rounded-xl bg-emerald-50 p-3 text-sm text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">
                Dataset passed the current automated quality checks.
              </div>
            )}
          </div>
        </motion.div>
      </div>
    </section>
  )
}
