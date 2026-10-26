"use client"

import { useEffect, useMemo, useState } from "react"
import { analysesApi } from "@/lib/api/analyses"
import { useDashboardContext } from "@/contexts/dashboard-context"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type {
  Analysis, MetricAggregation, MetricDefinition, MetricDefinitionInput, MetricPreview,
} from "@/types"

interface SourceColumn {
  name: string
  display_label?: string
  analysis_role?: string
  is_numeric?: boolean
}

const AGGREGATIONS: { value: MetricAggregation; label: string }[] = [
  { value: "sum", label: "Total (sum)" },
  { value: "average", label: "Average" },
  { value: "count", label: "Record count" },
  { value: "distinct_count", label: "Distinct recorded values" },
]

function eligible(column: SourceColumn, aggregation: MetricAggregation): boolean {
  if (aggregation === "count") return false
  if (aggregation === "sum" || aggregation === "average") {
    return Boolean(column.is_numeric && ["metric", "attribute"].includes(column.analysis_role ?? ""))
  }
  return ["identifier", "dimension", "flag", "attribute", "metric"].includes(column.analysis_role ?? "")
}

function errorMessage(error: unknown): string {
  const response = error as { response?: { data?: { detail?: string } } }
  return response?.response?.data?.detail ?? "Could not calculate this metric. Please try again."
}

export function MetricDefinitionsPanel({ analysis }: { analysis: Analysis }) {
  const dashboard = useDashboardContext()
  const [definitions, setDefinitions] = useState<MetricDefinition[]>([])
  const [draft, setDraft] = useState<MetricDefinitionInput>({ name: "", aggregation: "sum", column_name: null })
  const [editingFamily, setEditingFamily] = useState<string | null>(null)
  const [preview, setPreview] = useState<MetricPreview | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const schema = useMemo(() => {
    const raw = analysis.metadata?.schema
    return Array.isArray(raw) ? raw.filter((item): item is SourceColumn =>
      Boolean(item && typeof item === "object" && typeof item.name === "string")) : []
  }, [analysis.metadata])
  const available = schema.filter((column) => eligible(column, draft.aggregation))
  const normalized = { ...draft, name: draft.name.trim() }
  const previewMatches = preview !== null && JSON.stringify(preview.definition) === JSON.stringify(normalized)
  const pinnedIds = dashboard?.layout?.spec.metric_family_ids ?? []
  const pinned = pinnedIds.map((id) => definitions.find((item) => item.family_id === id))
    .filter((item): item is MetricDefinition => item !== undefined)

  useEffect(() => {
    let active = true
    analysesApi.listMetrics(analysis.id).then((items) => {
      if (active) setDefinitions(items)
    }).catch((cause) => {
      if (active) setError(errorMessage(cause))
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => { active = false }
  }, [analysis.id])

  function update(next: MetricDefinitionInput) {
    setDraft(next)
    setPreview(null)
    setError(null)
  }

  async function handlePreview() {
    setBusy(true)
    setError(null)
    try {
      setPreview(await analysesApi.previewMetric(analysis.id, normalized))
    } catch (cause) {
      setError(errorMessage(cause))
    } finally {
      setBusy(false)
    }
  }

  async function handleApprove() {
    if (!previewMatches) return
    setBusy(true)
    setError(null)
    try {
      const approved = editingFamily
        ? await analysesApi.reviseMetric(analysis.id, editingFamily, normalized)
        : await analysesApi.approveMetric(analysis.id, normalized)
      setDefinitions((current) => [
        ...current.filter((item) => item.family_id !== approved.family_id), approved,
      ])
      setDraft({ name: "", aggregation: "sum", column_name: null })
      setEditingFamily(null)
      setPreview(null)
    } catch (cause) {
      setError(errorMessage(cause))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="space-y-4 rounded-2xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900/60">
      {pinned.length > 0 && (
        <div>
          <h2 className="mb-1 font-semibold text-zinc-900 dark:text-white">Saved metric cards</h2>
          <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">Calculated across the saved dataset. Interactive filters do not change these values.</p>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {pinned.map((item) => (
              <div key={item.family_id} className="rounded-xl border border-violet-200 bg-gradient-to-br from-violet-100 via-white to-cyan-50 p-4 dark:border-violet-800 dark:from-violet-950 dark:via-zinc-900 dark:to-cyan-950">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-semibold text-zinc-800 dark:text-zinc-100">{item.name}</span>
                  <Button size="sm" variant="ghost" disabled={dashboard?.saving}
                    onClick={() => void dashboard?.edit("unpin_metric", undefined, item.family_id)}>Remove</Button>
                </div>
                <strong className="mt-2 block text-3xl text-violet-800 dark:text-violet-200">
                  {item.value == null ? "—" : new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(item.value)}
                </strong>
                <p className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">{AGGREGATIONS.find((option) => option.value === item.aggregation)?.label}{item.column_name ? ` of ${item.column_name}` : ""} · {item.row_count?.toLocaleString() ?? "?"} rows</p>
                {item.sample_truncated && <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">Calculated on the imported sample.</p>}
              </div>
            ))}
          </div>
        </div>
      )}
      <details className="rounded-xl border border-zinc-200 p-4 dark:border-zinc-700">
      <summary className="cursor-pointer text-sm font-semibold text-violet-700 dark:text-violet-300">
        {pinned.length > 0 ? "Manage approved metrics" : "Create and add an approved metric"}
      </summary>
      <div className="mt-4 space-y-4">
      <div>
        <h2 className="font-semibold text-zinc-900 dark:text-white">Approved metrics</h2>
        <p className="text-sm text-zinc-500">Define a calculation for this dataset, then add it to the saved dashboard.</p>
      </div>
      {loading ? <p className="text-sm text-zinc-500">Loading definitions…</p> : definitions.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2">
          {definitions.map((item) => (
            <div key={item.family_id} className="rounded-xl border border-zinc-200 p-4 dark:border-zinc-700">
              <div className="flex items-start justify-between gap-2">
                <strong className="text-sm text-zinc-900 dark:text-white">{item.name}</strong>
                <Button size="sm" variant="ghost" onClick={() => {
                  setEditingFamily(item.family_id)
                  update({ name: item.name, aggregation: item.aggregation, column_name: item.column_name })
                }}>Revise</Button>
              </div>
              {dashboard?.layout && !pinnedIds.includes(item.family_id) && (
                <Button size="sm" variant="outline" disabled={dashboard.saving}
                  onClick={() => void dashboard.edit("pin_metric", undefined, item.family_id)}>Add to dashboard</Button>
              )}
              <p className="text-2xl font-bold text-zinc-900 dark:text-white">
                {item.value == null ? "—" : new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(item.value)}
              </p>
              <p className="text-xs text-zinc-500">{AGGREGATIONS.find((option) => option.value === item.aggregation)?.label}
                {item.column_name ? ` of ${item.column_name}` : ""} · version {item.version} · {item.row_count?.toLocaleString() ?? "?"} rows
              </p>
              {item.sample_truncated && <p className="mt-1 text-xs text-amber-700">Calculated on the imported sample, not the entire file.</p>}
            </div>
          ))}
        </div>
      )}
      <div className="grid gap-3 rounded-xl bg-zinc-50 p-4 dark:bg-zinc-800/50 sm:grid-cols-[1fr_1fr_1fr_auto] sm:items-end">
        <label className="text-xs font-medium text-zinc-600 dark:text-zinc-300">Metric name
          <Input className="mt-1" value={draft.name} maxLength={160} placeholder="e.g. Total sales"
            onChange={(event) => update({ ...draft, name: event.target.value })} />
        </label>
        <label className="text-xs font-medium text-zinc-600 dark:text-zinc-300">Calculation
          <select className="mt-1 h-10 w-full rounded-md border border-zinc-200 bg-white px-2 dark:border-zinc-700 dark:bg-zinc-900"
            value={draft.aggregation} onChange={(event) => {
              const aggregation = event.target.value as MetricAggregation
              const first = schema.find((column) => eligible(column, aggregation))
              update({ ...draft, aggregation, column_name: first?.name ?? null })
            }}>
            {AGGREGATIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>
        <label className="text-xs font-medium text-zinc-600 dark:text-zinc-300">Source column
          <select className="mt-1 h-10 w-full rounded-md border border-zinc-200 bg-white px-2 dark:border-zinc-700 dark:bg-zinc-900"
            disabled={draft.aggregation === "count" || available.length === 0}
            value={draft.aggregation === "count" ? "" : draft.column_name ?? ""}
            onChange={(event) => update({ ...draft, column_name: event.target.value || null })}>
            <option value="">{draft.aggregation === "count" ? "All records" : "Choose a column"}</option>
            {available.map((column) => <option key={column.name} value={column.name}>{column.display_label || column.name}</option>)}
          </select>
        </label>
        <Button variant="outline" disabled={busy || !normalized.name || (draft.aggregation !== "count" && !draft.column_name)}
          onClick={handlePreview}>Preview</Button>
      </div>
      {previewMatches && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-blue-200 bg-blue-50 p-4 dark:border-blue-900 dark:bg-blue-950/30">
          <p className="text-sm text-zinc-800 dark:text-zinc-200">
            Preview: <strong>{preview.value == null ? "No value" : new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(preview.value)}</strong>
            {` from ${preview.row_count.toLocaleString()} rows in ${preview.source_filename}.`}
            {preview.sample_truncated && " The imported data is a sample of the file."}
            {draft.aggregation === "distinct_count" && " Distinct values are not verified real-world entities."}
          </p>
          <Button disabled={busy} onClick={handleApprove}>{editingFamily ? "Approve revision" : "Approve metric"}</Button>
        </div>
      )}
      </div>
      </details>
      {error && <p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      {dashboard?.error && <p role="alert" className="text-sm text-amber-700 dark:text-amber-300">{dashboard.error}</p>}
    </section>
  )
}
