import { beforeEach, describe, expect, it, vi } from "vitest"
import type { ActiveFilter, ComparisonFilter, ComparisonPlan } from "@/types"
import { analysesApi } from "./analyses"

const mocks = vi.hoisted(() => ({ post: vi.fn() }))

vi.mock("@/lib/api/client", () => ({
  apiClient: {},
  get: vi.fn(),
  post: mocks.post,
  put: vi.fn(),
  del: vi.fn(),
  patch: vi.fn(),
}))

beforeEach(() => {
  vi.clearAllMocks()
  mocks.post.mockResolvedValue({})
})

describe("comparison requests", () => {
  it("serializes only canonical fields in all comparison filter collections", async () => {
    const filters: (ComparisonFilter & { display_label: string; selected: boolean })[] = [
      { column: "donor_id", op: "in", values: ["001", "D0001"], display_label: "Donor", selected: true },
    ]
    const cohortFilters = [
      { column: "AEP_MW", op: "gte" as const, values: [20000], display_label: "Power", draft: false },
    ]
    const returnFilters = [
      { column: "ratio", op: "lt" as const, values: [0.5], display_label: "Ratio", color: "purple" },
    ]
    const plan: ComparisonPlan = {
      aggregation: "retention",
      column: "donor_id",
      group_by: null,
      filters,
      cohort_filters: cohortFilters,
      return_filters: returnFilters,
      order: "desc",
      limit: 10,
    }
    const before = structuredClone(plan)

    await analysesApi.compare("report", plan)

    expect(mocks.post).toHaveBeenCalledWith("/analyses/report/compare", {
      aggregation: "retention",
      column: "donor_id",
      group_by: null,
      filters: [{ column: "donor_id", op: "in", values: ["001", "D0001"] }],
      cohort_filters: [{ column: "AEP_MW", op: "gte", values: [20000] }],
      return_filters: [{ column: "ratio", op: "lt", values: [0.5] }],
      order: "desc",
      limit: 10,
    })
    expect(plan).toEqual(before)
    const body = mocks.post.mock.calls[0][1] as ComparisonPlan
    expect(body).not.toBe(plan)
    for (const key of ["filters", "cohort_filters", "return_filters"] as const) {
      expect(body[key]).not.toBe(plan[key])
      expect(body[key]![0]).not.toBe(plan[key]![0])
      expect(body[key]![0].values).not.toBe(plan[key]![0].values)
    }
  })

  it("preserves an empty collection without adding omitted filter collections", async () => {
    await analysesApi.compare("report", { aggregation: "count", filters: [] })

    expect(mocks.post).toHaveBeenCalledWith("/analyses/report/compare", {
      aggregation: "count",
      filters: [],
    })
  })

  it("keeps dashboard query filter serialization unchanged", async () => {
    const filters: ActiveFilter[] = [
      { column: "channel", display_label: "Channel", op: "in", values: ["Online"] },
    ]

    await analysesApi.queryAnalysis("report", filters)

    expect(mocks.post).toHaveBeenCalledWith("/analyses/report/query", {
      filters: [{ column: "channel", op: "in", values: ["Online"] }],
    })
    expect(filters[0].display_label).toBe("Channel")
  })
})
