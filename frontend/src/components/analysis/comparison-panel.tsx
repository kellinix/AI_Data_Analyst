"use client"

import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { analysesApi } from "@/lib/api/analyses"
import { useFilterContext } from "@/contexts/filter-context"
import { Button } from "@/components/ui/button"
import { EntryViewer } from "./entry-viewer"
import type { Analysis, ComparisonPlan, ComparisonResult } from "@/types"

export function ComparisonFigures({ analysisId, result }: { analysisId: string; result: ComparisonResult }) {
  return <div className="space-y-3"><p className="whitespace-pre-line text-sm">{result.answer}</p><p className="text-xs text-zinc-500 dark:text-zinc-400">{result.scope}</p>
    {result.groups.map((group, i) => <div key={i} className="rounded-xl border p-3 dark:border-zinc-700"><p className="text-sm font-medium">{group.group ?? (result.plan.group_by ? "Not provided" : result.title)}: {group.value == null ? "Not available" : group.value.toLocaleString(undefined, { maximumFractionDigits: 2 })}{group.value == null ? "" : result.value_unit}</p><p className="mt-1 text-xs text-zinc-500">Based on {group.entries.toLocaleString()} entries; {group.supplied_values.toLocaleString()} filled-in values.</p><EntryViewer analysisId={analysisId} request={{ kind: "comparison", comparison: result.plan, evidence_revision: result.evidence_revision, group_value: group.group_value }} title="View supporting records" /></div>)}
  </div>
}

export function ComparisonPanel({ analysis }: { analysis: Analysis }) {
  const schema = (analysis.metadata?.schema ?? []) as { name: string; analysis_role?: string; is_numeric?: boolean; display_label?: string; semantic_type?: string }[]
  const measures = schema.filter((c) => c.analysis_role === "metric" && c.is_numeric)
  const groups = schema.filter((c) => ["dimension", "flag"].includes(c.analysis_role ?? ""))
  const [column, setColumn] = useState("")
  const [group, setGroup] = useState("")
  const [aggregation, setAggregation] = useState<"sum" | "average" | "count">("average")
  const { activeFilters } = useFilterContext()
  const compare = useMutation({ mutationFn: (plan: ComparisonPlan) => analysesApi.compare(analysis.id, plan) })
  if (!groups.length) return null
  return <section className="space-y-4 rounded-2xl border bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900/60"><h2 className="font-semibold">Compare groups</h2><p className="text-sm text-zinc-600 dark:text-zinc-300">Choose what to compare. Zephyr works out the figures from your file.</p>
    <div className="flex flex-wrap gap-3"><select aria-label="What to calculate" className="rounded-lg border bg-transparent p-2" value={aggregation} onChange={(e) => setAggregation(e.target.value as typeof aggregation)}><option value="sum" disabled={measures.some((c) => c.name === column && ["average_metric", "percentage"].includes(c.semantic_type ?? ""))}>Total</option><option value="average">Average per entry</option><option value="count">Number of entries</option></select>
      {aggregation !== "count" && <select aria-label="Measure" className="rounded-lg border bg-transparent p-2" value={column} onChange={(e) => { setColumn(e.target.value); if (measures.some((c) => c.name === e.target.value && ["average_metric", "percentage"].includes(c.semantic_type ?? ""))) setAggregation("average") }}><option value="">Choose a measure</option>{measures.map((c) => <option key={c.name} value={c.name}>{c.display_label ?? c.name.replaceAll("_", " ").replace(/\bavg\b/gi, "average").replace(/\bpct\b/gi, "percentage")}</option>)}</select>}
      <select aria-label="Group" className="rounded-lg border bg-transparent p-2" value={group} onChange={(e) => setGroup(e.target.value)}><option value="">Choose a group</option>{groups.map((c) => <option key={c.name} value={c.name}>{c.display_label ?? c.name.replaceAll("_", " ").replace(/\bavg\b/gi, "average").replace(/\bpct\b/gi, "percentage")}</option>)}</select>
      <Button disabled={!group || (aggregation !== "count" && !column) || compare.isPending} onClick={() => compare.mutate({ aggregation, column: aggregation === "count" ? null : column, group_by: group, filters: activeFilters })}>{compare.isPending ? "Comparing…" : "Compare"}</Button></div>
    <p className="text-xs text-zinc-500">{activeFilters.length ? "Uses your currently selected filters." : "Uses all entries in this report."} Results are ordered from highest to lowest.</p>
    {compare.error && <p role="alert" className="text-sm text-red-600">{(compare.error as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? "Could not compare these groups. Please try again."}</p>}
    {compare.data && <ComparisonFigures analysisId={analysis.id} result={compare.data} />}
  </section>
}
