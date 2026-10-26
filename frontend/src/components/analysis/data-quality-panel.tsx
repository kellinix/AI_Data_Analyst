"use client"

import { motion } from "framer-motion"
import { CheckCircle2, Database, ShieldAlert } from "lucide-react"
import { Badge } from "@/components/ui/badge"

import { EntryViewer } from "./entry-viewer"
import type { EvidenceEntryRequest } from "@/types"

interface Issue {
  evidence_link?: EvidenceEntryRequest
  type?: string
  column?: string | null
  column_label?: string | null
  severity?: string
  description: string
}
interface Quality {
  headline?: string
  score?: number
  scope?: string
  score_explanation?: string
  issues?: Issue[]
  empty_fields?: string[]
  source_quality?: { scope?: string; issues?: Issue[] }
}

export function DataQualityPanel({ metadata, analysisId }: { metadata: Record<string, unknown>; analysisId?: string }) {
  const quality = metadata.data_quality as Quality | undefined
  if (!quality) return null
  const issues = quality.issues ?? []
  const needsReview = issues.some((issue) => issue.severity !== "low")
  const cleaning = (metadata.upload_context as { cleaning?: { enabled?: boolean; report?: { input_rows?: number; output_rows?: number; capped_outlier_values?: number } } } | undefined)?.cleaning
  const evidence = metadata.analysis_evidence as { limitations?: string[]; entity_counts?: { column: string; distinct_values: number; count_basis: string }[]; cleaning?: { row_changes?: { reason: string; rows: number }[] } } | undefined

  return <section>
    <div className="mb-4 flex items-center gap-2">
      <Database className="h-5 w-5 text-teal-600" />
      <h2 className="text-base font-semibold text-zinc-900 dark:text-white">What to check in your file</h2>
    </div>
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
      className="rounded-2xl border bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/60">
      <div className="flex items-center gap-3">
        {needsReview ? <ShieldAlert className="h-5 w-5 text-amber-500" /> : <CheckCircle2 className="h-5 w-5 text-emerald-500" />}
        <h3 className="text-sm font-semibold text-zinc-900 dark:text-white">{quality.headline ?? (issues.length ? "A few things are worth checking" : "No problems found by these checks")}</h3>
      </div>
      <p className="mt-3 text-sm leading-relaxed text-zinc-600 dark:text-zinc-300">{quality.scope ?? "We checked for blanks, repeated entries and unusual numbers. These checks cannot confirm that every entry is correct."}</p>
      <div className="mt-4 space-y-3">
        {!!quality.empty_fields?.length && <p className="text-sm text-zinc-600 dark:text-zinc-300">Completely blank fields: {quality.empty_fields.join(", ")}. Check whether you need them.</p>}
        {issues.slice(0, 6).map((issue, index) => <div key={index} className="flex items-start justify-between gap-4 rounded-xl bg-zinc-50 p-3 dark:bg-zinc-800/50">
          <div><p className="text-sm font-medium text-zinc-800 dark:text-zinc-100">{issue.column_label ?? issue.column?.replaceAll("_", " ") ?? "Your whole file"}</p>
            <p className="mt-1 text-sm leading-relaxed text-zinc-600 dark:text-zinc-300">{issue.description}</p>{analysisId && issue.evidence_link && <EntryViewer analysisId={analysisId} request={issue.evidence_link} />}</div>
          <Badge variant={issue.severity === "high" || issue.severity === "critical" ? "warning" : "secondary"} className="shrink-0 text-[10px]">{issue.severity === "high" || issue.severity === "critical" ? "Check first" : issue.severity === "low" ? "For reference" : "Worth reviewing"}</Badge>
        </div>)}
      </div>
      {quality.source_quality && <div className="mt-5 border-t pt-4 dark:border-zinc-800">
        <h3 className="text-sm font-semibold text-zinc-900 dark:text-white">Your original file</h3>
        <p className="mt-2 text-sm leading-relaxed text-zinc-600 dark:text-zinc-300">{quality.source_quality.scope}</p>
        {quality.source_quality.issues?.map((issue, index) => <p key={index} className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">{issue.column}: {issue.description}</p>)}
      </div>}
      {cleaning?.enabled && <div className="mt-5 border-t pt-4 dark:border-zinc-800">
        <h3 className="text-sm font-semibold text-zinc-900 dark:text-white">What changed during cleaning</h3>
        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">{cleaning.report?.input_rows?.toLocaleString()} entries became {cleaning.report?.output_rows?.toLocaleString()} entries.</p>
        {evidence?.cleaning?.row_changes?.map((change, index) => <p key={index} className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">{change.reason}: {change.rows.toLocaleString()} entries.</p>)}
        {!!cleaning.report?.capped_outlier_values && <p className="mt-2 text-sm text-amber-700 dark:text-amber-300">Cleaning adjusted {cleaning.report.capped_outlier_values.toLocaleString()} unusually high or low values. Totals and averages may differ from the original file.</p>}
      </div>}
      <details className="mt-5 border-t pt-4 text-sm dark:border-zinc-800">
        <summary className="cursor-pointer font-medium text-violet-700 dark:text-violet-300">See check details</summary>
        <p className="mt-3 text-zinc-600 dark:text-zinc-300">File check score: {quality.score ?? "Not available"}/100.</p>
        <p className="mt-2 leading-relaxed text-zinc-600 dark:text-zinc-300">{quality.score_explanation ?? "The score reflects the checks we ran. It is not a guarantee that every entry is correct."}</p>
      </details>
    </motion.div>
    {evidence && <details className="mt-4 rounded-2xl border bg-white p-4 text-sm dark:border-zinc-800 dark:bg-zinc-900/60">
      <summary className="cursor-pointer font-medium text-zinc-900 dark:text-white">About these figures</summary>
      {evidence.entity_counts?.map((item) => <p key={item.column} className="mt-3 text-zinc-600 dark:text-zinc-300">{item.column}: {item.distinct_values.toLocaleString()} different values. {item.count_basis}</p>)}
      {evidence.limitations?.map((note, index) => <p key={index} className="mt-3 text-zinc-600 dark:text-zinc-300">{note}</p>)}
    </details>}
  </section>
}
