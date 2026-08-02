"use client"

import { Filter, Loader2, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useFilterContext } from "@/contexts/filter-context"
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
      <DropdownMenuContent
        align="start"
        sideOffset={8}
        className="z-[70] w-56 border-zinc-200 shadow-lg dark:border-zinc-700"
      >
        {topValues.map((v) => (
          <DropdownMenuCheckboxItem
            key={v.value}
            checked={isFilterActive(column.column, v.value)}
            onCheckedChange={() => toggleValue(column.column, v.value)}
            onSelect={(e) => e.preventDefault()}
          >
            {v.value}
            <span className="ml-auto pl-3 text-xs text-zinc-400">{v.count.toLocaleString()}</span>
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

export function SlicerBar({ filterableColumns }: SlicerBarProps) {
  const { activeFilters, toggleValue, clearAll, isRefetching, lastError, rowCount, sampleRowCount } =
    useFilterContext()
  const categorical = filterableColumns.filter((c) => c.kind === "categorical")

  if (categorical.length === 0) return null

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
        {isRefetching && <Loader2 className="h-4 w-4 animate-spin text-zinc-400" />}
        {activeFilters.length > 0 && rowCount !== null && sampleRowCount !== null && (
          <span className="text-xs text-zinc-400">
            {rowCount.toLocaleString()} of {sampleRowCount.toLocaleString()} rows
          </span>
        )}
      </div>

      {activeFilters.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          {activeFilters.flatMap((filter) =>
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
    </section>
  )
}
