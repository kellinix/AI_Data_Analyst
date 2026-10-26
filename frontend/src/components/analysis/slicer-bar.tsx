"use client"

import { useEffect, useState } from "react"
import { Filter, Loader2, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useFilterContext } from "@/contexts/filter-context"
import { useDashboardContext } from "@/contexts/dashboard-context"
import type { FilterableColumn } from "@/types"

interface SlicerBarProps {
  filterableColumns: FilterableColumn[]
}

function SlicerDropdown({ column }: { column: FilterableColumn }) {
  const { toggleValue, isFilterActive } = useFilterContext()
  const topValues = column.top_values ?? []
  if (topValues.length === 0) return null

  const activeCount = topValues.filter((v) => isFilterActive(column.column, v.value)).length
  const hasMore = (column.unique_count ?? topValues.length) > topValues.length

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="gap-1.5">
          {column.display_label}
          {activeCount > 0 && (
            <span className="ml-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-blue-600 text-[10px] font-semibold text-white">
              {activeCount}
            </span>
          )}
        </Button>
      </DropdownMenuTrigger>
      {/* A value can be a whole sentence — "Exempt under Section 43 of the
          Freedom of Information Act 2000 (Commercial Interests)" — so without a
          height cap the menu grew past the viewport and ran down over the
          charts. Cap it and scroll; the base sets overflow-hidden. */}
      <DropdownMenuContent
        align="start"
        sideOffset={8}
        className="z-[70] max-h-[60vh] w-72 overflow-y-auto border-zinc-200 shadow-lg dark:border-zinc-700"
      >
        {topValues.map((v) => (
          <DropdownMenuCheckboxItem
            key={v.value}
            checked={isFilterActive(column.column, v.value)}
            onCheckedChange={() => toggleValue(column.column, v.value)}
            onSelect={(e) => e.preventDefault()}
          >
            <span className="min-w-0 flex-1 truncate" title={v.label ?? v.value}>
              {v.label ?? v.value}
            </span>
            <span className="ml-auto shrink-0 pl-3 text-xs text-zinc-400">
              {v.count.toLocaleString()}
            </span>
          </DropdownMenuCheckboxItem>
        ))}
        {hasMore && (
          <p className="px-2 py-1.5 text-[11px] text-zinc-400">
            Top {topValues.length} of {column.unique_count} values
          </p>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function DateRangeFilter({ column }: { column: FilterableColumn }) {
  const { activeFilters, setDateRange, clearFilter } = useFilterContext()
  const active = activeFilters.find((filter) => filter.column === column.column && filter.op === "date_between")
  const [start, setStart] = useState("")
  const [end, setEnd] = useState("")

  useEffect(() => {
    if (!active) { setStart(""); setEnd("") }
  }, [active])

  return (
    <div className="flex flex-wrap items-end gap-2 rounded-md border border-zinc-200 px-3 py-2 dark:border-zinc-700">
      <span className="self-center text-xs font-medium text-zinc-600 dark:text-zinc-300">{column.display_label}</span>
      <label className="text-xs text-zinc-500">From
        <Input type="date" aria-label={`${column.display_label} from`} className="mt-1 h-8 w-36"
          min={column.min_date ?? undefined} max={end || column.max_date || undefined}
          value={start} onChange={(event) => setStart(event.target.value)} />
      </label>
      <label className="text-xs text-zinc-500">To
        <Input type="date" aria-label={`${column.display_label} to`} className="mt-1 h-8 w-36"
          min={start || column.min_date || undefined} max={column.max_date ?? undefined}
          value={end} onChange={(event) => setEnd(event.target.value)} />
      </label>
      <Button size="sm" variant="outline" disabled={!start || !end || start > end || (active?.values[0] === start && active?.values[1] === end)}
        onClick={() => setDateRange(column.column, start, end)}>Apply</Button>
      {active && <Button size="sm" variant="ghost" onClick={() => clearFilter(column.column)}>Clear</Button>}
    </div>
  )
}

function NumericRangeFilter({ columns }: { columns: FilterableColumn[] }) {
  const { activeFilters, setNumericRange, clearFilter } = useFilterContext()
  const [selected, setSelected] = useState(columns[0]?.column ?? "")
  const column = columns.find((candidate) => candidate.column === selected) ?? columns[0]
  const active = activeFilters.find((filter) => filter.column === column?.column && filter.op === "between")
  const [minimum, setMinimum] = useState("")
  const [maximum, setMaximum] = useState("")

  useEffect(() => {
    setMinimum(active ? String(active.values[0]) : "")
    setMaximum(active ? String(active.values[1]) : "")
  }, [selected, active])

  if (!column) return null
  const low = Number(minimum)
  const high = Number(maximum)
  const valid = minimum !== "" && maximum !== "" && Number.isFinite(low) && Number.isFinite(high)
    && low <= high && (column.min == null || low >= column.min)
    && (column.max == null || high <= column.max)

  return (
    <div className="flex flex-wrap items-end gap-2 rounded-md border border-zinc-200 px-3 py-2 dark:border-zinc-700">
      <label className="text-xs text-zinc-500">Measure
        <select aria-label="Numeric filter measure" className="mt-1 block h-8 max-w-44 rounded-md border border-zinc-200 bg-white px-2 text-sm text-zinc-800 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          value={column.column} onChange={(event) => setSelected(event.target.value)}>
          {columns.map((candidate) => <option key={candidate.column} value={candidate.column}>{candidate.display_label}</option>)}
        </select>
      </label>
      <label className="text-xs text-zinc-500">Min
        <Input type="number" aria-label={`${column.display_label} minimum`} className="mt-1 h-8 w-28"
          min={column.min ?? undefined} max={column.max ?? undefined} step="any" placeholder={String(column.min ?? "")}
          value={minimum} onChange={(event) => setMinimum(event.target.value)} />
      </label>
      <label className="text-xs text-zinc-500">Max
        <Input type="number" aria-label={`${column.display_label} maximum`} className="mt-1 h-8 w-28"
          min={column.min ?? undefined} max={column.max ?? undefined} step="any" placeholder={String(column.max ?? "")}
          value={maximum} onChange={(event) => setMaximum(event.target.value)} />
      </label>
      <Button size="sm" variant="outline" disabled={!valid || (active?.values[0] === low && active?.values[1] === high)}
        onClick={() => setNumericRange(column.column, low, high)}>Apply</Button>
      {active && <Button size="sm" variant="ghost" onClick={() => clearFilter(column.column)}>Clear</Button>}
    </div>
  )
}

export function SlicerBar({ filterableColumns }: SlicerBarProps) {
  const dashboard = useDashboardContext()
  const { activeFilters, toggleValue, clearFilter, clearAll, isRefetching, lastError, rowCount, sampleRowCount } =
    useFilterContext()
  const categorical = filterableColumns.filter((c) => c.kind === "categorical")
  const dates = filterableColumns.filter((c) => c.kind === "date")
  const numeric = filterableColumns.filter((c) => c.kind === "numeric")

  if (categorical.length === 0 && dates.length === 0 && numeric.length === 0) return null

  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="mr-1 flex items-center gap-1.5 text-sm font-medium text-zinc-500 dark:text-zinc-400">
          <Filter className="h-3.5 w-3.5" />
          Filter
        </div>
        {categorical.map((column) => (
          <SlicerDropdown key={column.column} column={column} />
        ))}
        {dates.map((column) => (
          <DateRangeFilter key={column.column} column={column} />
        ))}
        {numeric.length > 0 && <NumericRangeFilter columns={numeric} />}
        {isRefetching && <Loader2 className="h-4 w-4 animate-spin text-zinc-400" />}
        {dashboard?.layout && (
          <Button size="sm" variant="outline" disabled={dashboard.saving ||
            JSON.stringify(activeFilters.map(({ column, op, values }) => ({ column, op, values }))) ===
            JSON.stringify(dashboard.layout.spec.saved_filters)}
            onClick={() => void dashboard.edit("save_filters", undefined, undefined, activeFilters)}>
            Save filters
          </Button>
        )}
        {activeFilters.length > 0 && rowCount !== null && sampleRowCount !== null && (
          <span className="text-xs text-zinc-400">
            {rowCount.toLocaleString()} of {sampleRowCount.toLocaleString()} rows
          </span>
        )}
      </div>

      {activeFilters.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          {activeFilters.filter((filter) => filter.op === "date_between").map((filter) => (
            <button key={filter.column} onClick={() => clearFilter(filter.column)}
              className="flex items-center gap-1 rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700 dark:bg-blue-950/40 dark:text-blue-300">
              {filter.display_label}: {filter.values[0]} to {filter.values[1]} <X className="h-3 w-3" />
            </button>
          ))}
          {activeFilters.filter((filter) => filter.op === "between").map((filter) => (
            <button key={filter.column} onClick={() => clearFilter(filter.column)}
              className="flex items-center gap-1 rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700 dark:bg-blue-950/40 dark:text-blue-300">
              {filter.display_label}: {filter.values[0]} to {filter.values[1]} <X className="h-3 w-3" />
            </button>
          ))}
          {activeFilters.filter((filter) => filter.op === "in").flatMap((filter) =>
            filter.values.map((value) => (
              <button
                key={`${filter.column}-${value}`}
                onClick={() => toggleValue(filter.column, value)}
                className="flex items-center gap-1 rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700 transition-colors hover:bg-blue-100 dark:bg-blue-950/40 dark:text-blue-300 dark:hover:bg-blue-950/60"
              >
                {filter.display_label}: {value}
                <X className="h-3 w-3" />
              </button>
            ))
          )}
          <button
            onClick={clearAll}
            className="text-xs font-medium text-zinc-400 underline-offset-2 hover:text-zinc-600 hover:underline dark:hover:text-zinc-200"
          >
            Clear all
          </button>
        </div>
      )}

      {lastError && (
        <p className="text-xs text-amber-600 dark:text-amber-400">{lastError}</p>
      )}
      {dashboard?.error && <p role="alert" className="text-xs text-amber-700 dark:text-amber-300">{dashboard.error}</p>}
    </section>
  )
}
