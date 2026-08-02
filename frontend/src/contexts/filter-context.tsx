"use client"

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react"
import { analysesApi } from "@/lib/api/analyses"
import type { ActiveFilter, ChartPatch, FilterableColumn, KpiPatch } from "@/types"

interface FilterContextValue {
  activeFilters: ActiveFilter[]
  toggleValue: (column: string, value: string | number) => void
  clearAll: () => void
  isFilterActive: (column: string, value: string | number) => boolean
  chartPatches: Record<string, ChartPatch>
  kpiPatches: Record<string, KpiPatch>
  isRefetching: boolean
  lastError: string | null
  rowCount: number | null
  sampleRowCount: number | null
}

const NOOP_CONTEXT: FilterContextValue = {
  activeFilters: [],
  toggleValue: () => {},
  clearAll: () => {},
  isFilterActive: () => false,
  chartPatches: {},
  kpiPatches: {},
  isRefetching: false,
  lastError: null,
  rowCount: null,
  sampleRowCount: null,
}

const FilterContext = createContext<FilterContextValue | null>(null)

const DEBOUNCE_MS = 400

export function FilterProvider({
  analysisId,
  filterableColumns,
  children,
}: {
  analysisId: string
  filterableColumns: FilterableColumn[]
  children: ReactNode
}) {
  const [activeFilters, setActiveFilters] = useState<ActiveFilter[]>([])
  const [chartPatches, setChartPatches] = useState<Record<string, ChartPatch>>({})
  const [kpiPatches, setKpiPatches] = useState<Record<string, KpiPatch>>({})
  const [isRefetching, setIsRefetching] = useState(false)
  const [lastError, setLastError] = useState<string | null>(null)
  const [rowCount, setRowCount] = useState<number | null>(null)
  const [sampleRowCount, setSampleRowCount] = useState<number | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Guards against an older, slower request overwriting a newer one's result.
  const requestIdRef = useRef(0)

  const columnLabels = useMemo(
    () => Object.fromEntries(filterableColumns.map((c) => [c.column, c.display_label])),
    [filterableColumns]
  )

  const runQuery = useCallback(
    async (filters: ActiveFilter[]) => {
      const requestId = ++requestIdRef.current
      setIsRefetching(true)
      try {
        const result = await analysesApi.queryAnalysis(analysisId, filters)
        if (requestId !== requestIdRef.current) return
        setChartPatches(Object.fromEntries(result.charts.map((c) => [c.id, c])))
        setKpiPatches(Object.fromEntries(result.kpis.map((k) => [k.insight_id, k])))
        setRowCount(result.row_count)
        setSampleRowCount(result.sample_row_count)
        setLastError(null)
      } catch {
        if (requestId !== requestIdRef.current) return
        // Keep whatever charts/KPIs were last successfully patched — never
        // blank the dashboard because one refresh failed.
        setLastError("Couldn't refresh with the current filters — showing the last results.")
      } finally {
        if (requestId === requestIdRef.current) setIsRefetching(false)
      }
    },
    [analysisId]
  )

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)

    if (activeFilters.length === 0) {
      requestIdRef.current++
      setChartPatches({})
      setKpiPatches({})
      setIsRefetching(false)
      setLastError(null)
      setRowCount(null)
      setSampleRowCount(null)
      return
    }

    debounceRef.current = setTimeout(() => {
      void runQuery(activeFilters)
    }, DEBOUNCE_MS)

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [activeFilters, runQuery])

  const toggleValue = useCallback(
    (column: string, value: string | number) => {
      setActiveFilters((prev) => {
        const existing = prev.find((f) => f.column === column)
        if (!existing) {
          return [
            ...prev,
            {
              column,
              display_label: columnLabels[column] ?? column,
              op: "in" as const,
              values: [value],
            },
          ]
        }
        const hasValue = existing.values.includes(value)
        const nextValues = hasValue
          ? existing.values.filter((v) => v !== value)
          : [...existing.values, value]
        if (nextValues.length === 0) {
          return prev.filter((f) => f.column !== column)
        }
        return prev.map((f) => (f.column === column ? { ...f, values: nextValues } : f))
      })
    },
    [columnLabels]
  )

  const clearAll = useCallback(() => setActiveFilters([]), [])

  const isFilterActive = useCallback(
    (column: string, value: string | number) =>
      activeFilters.some((f) => f.column === column && f.values.includes(value)),
    [activeFilters]
  )

  const value = useMemo<FilterContextValue>(
    () => ({
      activeFilters,
      toggleValue,
      clearAll,
      isFilterActive,
      chartPatches,
      kpiPatches,
      isRefetching,
      lastError,
      rowCount,
      sampleRowCount,
    }),
    [
      activeFilters,
      toggleValue,
      clearAll,
      isFilterActive,
      chartPatches,
      kpiPatches,
      isRefetching,
      lastError,
      rowCount,
      sampleRowCount,
    ]
  )

  return <FilterContext.Provider value={value}>{children}</FilterContext.Provider>
}

/** Safe to call from components that might render outside a FilterProvider
 * (e.g. the public share view, which doesn't support live filtering) — falls
 * back to an inert "no filters, nothing patched" context instead of throwing. */
export function useFilterContext(): FilterContextValue {
  return useContext(FilterContext) ?? NOOP_CONTEXT
}
