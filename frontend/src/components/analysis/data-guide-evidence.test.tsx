// @vitest-environment jsdom

import type { ReactNode } from "react"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import type { ActiveFilter, ComparisonResult, EvidenceEntries } from "@/types"
import { ComparisonFigures } from "./comparison-panel"
import { SlicerBar } from "./slicer-bar"

const state = vi.hoisted(() => ({ entries: {} as EvidenceEntries, request: {} as Record<string, unknown>,
  filters: [] as ActiveFilter[], toggleValue: vi.fn(),
}))
vi.mock("@tanstack/react-query", () => ({
  useQuery: ({ queryKey }: { queryKey: unknown[] }) => {
    state.request = queryKey[2] as Record<string, unknown>
    return { data: state.entries, isPending: false, isFetching: false }
  },
  useMutation: vi.fn(),
}))
vi.mock("@/contexts/filter-context", () => ({ useFilterContext: () => ({ activeFilters: state.filters,
  toggleValue: state.toggleValue, clearFilter: vi.fn(), clearAll: vi.fn(), isFilterActive: () => true,
  isRefetching: false, lastError: null, rowCount: null, sampleRowCount: null,
}) }))
vi.mock("@/contexts/dashboard-context", () => ({ useDashboardContext: () => null }))
vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({ children, open }: { children: ReactNode; open: boolean }) => open ? <div>{children}</div> : null,
  DialogContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: ReactNode }) => <h2>{children}</h2>,
}))
afterEach(() => { cleanup(); state.filters = [] })

it.each([true, false])("displays guide meanings when supplied (%s) and drills into the raw group", (guided) => {
  state.entries = { matched_entries: 1, offset: 0, limit: 25, scope: "This report", has_more: false,
    columns: [{ name: "status", label: "Marital status" }],
    entries: [{ entry_number: 1, values: { status: "M" }, ...(guided ? { display_values: { status: "Married (M)" } } : {}) }],
  }
  const result: ComparisonResult = { evidence_revision: "revision", title: "Amount by status", answer: "The recorded total is 10.",
    scope: "This report", matched_entries: 1, group_count: 1, plan: { aggregation: "sum", column: "amount", group_by: "status" },
    groups: [{ group: "M", group_value: "M", ...(guided ? { display_label: "Married (M)" } : {}),
      value: 10, entries: 1, supplied_values: 1 }],
  }
  render(<ComparisonFigures analysisId="analysis" result={result} />)
  expect(screen.getByText(guided ? "Married (M): 10" : "M: 10")).toBeTruthy()
  fireEvent.click(screen.getByRole("button", { name: "View supporting records" }))
  expect(screen.getByRole("cell", { name: guided ? "Married (M)" : "M" })).toBeTruthy()
  expect(state.request.group_value).toBe("M")
  expect(state.entries.entries[0].values.status).toBe("M")
})

it("active filter labels use their supplied meaning while clearing the recorded code", () => {
  state.filters = [{ column: "status", display_label: "Marital status", op: "in", values: ["M"] }]
  render(<SlicerBar filterableColumns={[{ column: "status", display_label: "Marital status", role: "dimension",
    kind: "categorical", top_values: [{ value: "M", count: 3, label: "Married (M)" }] }]} />)
  state.toggleValue.mockClear()
  fireEvent.click(screen.getByRole("button", { name: "Marital status: Married (M)" }))
  expect(state.toggleValue).toHaveBeenCalledWith("status", "M")
})
