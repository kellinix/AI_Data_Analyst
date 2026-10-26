import { describe, expect, it } from "vitest"
import { parseDashboardCommand } from "./dashboard-commands"
import type { ChartConfig, MetricDefinition } from "@/types"

const charts = [
  { id: "sales", title: "Sales by region" },
  { id: "returns", title: "Returns" },
] as ChartConfig[]
const metrics = [{ family_id: "metric-1", name: "Total sales" }] as MetricDefinition[]

describe("dashboard text commands", () => {
  it("resolves only exact saved chart and approved metric names", () => {
    expect(parseDashboardCommand('hide chart "Sales by region"', charts, metrics).command)
      .toEqual({ action: "hide", chartId: "sales" })
    expect(parseDashboardCommand('pin metric "Total sales"', charts, metrics).command)
      .toEqual({ action: "pin_metric", metricFamilyId: "metric-1" })
    expect(parseDashboardCommand('colour chart "Returns" ocean', charts, metrics).command)
      .toEqual({ action: "set_palette", chartId: "returns", palette: "ocean" })
    expect(parseDashboardCommand("hide chart Sales", charts, metrics).error).toContain("exact chart title")
  })

  it("keeps ordinary data questions out of the editor", () => {
    expect(parseDashboardCommand("Show me any unusual patterns", charts, metrics))
      .toEqual({ command: null, error: null })
  })
})
