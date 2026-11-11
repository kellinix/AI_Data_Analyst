// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, expect, it, vi } from "vitest"
import type { ChartConfig } from "@/types"
import { ChartsGrid } from "./charts-grid"

const captured = vi.hoisted(() => ({ option: {} as Record<string, unknown>,
  onEvents: {} as { click?: (parameters: { name: string }) => void }, toggleValue: vi.fn(),
}))

vi.mock("next/dynamic", () => ({ default: () => (props: { option: Record<string, unknown>; onEvents: typeof captured.onEvents }) => {
  captured.option = props.option
  captured.onEvents = props.onEvents
  return null
} }))
vi.mock("next-themes", () => ({ useTheme: () => ({ resolvedTheme: "light" }) }))
vi.mock("framer-motion", () => ({ motion: { div: ({ children }: { children: ReactNode }) => <div>{children}</div> } }))
vi.mock("@/contexts/filter-context", () => ({ useFilterContext: () => ({
  chartPatches: {}, activeFilters: [], toggleValue: captured.toggleValue, isRefetching: false,
}) }))
vi.mock("@/contexts/dashboard-context", () => ({ useDashboardContext: () => null }))

afterEach(cleanup)

function lineChart(periods: number, names: string[], previewLimit?: number): ChartConfig {
  const labels = Array.from({ length: periods }, (_, index) => String(index))
  const series = names.map((name, metric) => ({
    type: "line", name, data: labels.map((_, index) => index + metric),
  }))
  const values = series.flatMap((item) => labels.map((period, index) => ({
    period, metric: item.name, value: item.data[index],
  })))
  return {
    id: "chart", type: "line", title: "Recorded figures by period", series: names,
    description: null, xAxis: "Period", yAxis: "Recorded value", color_scheme: [],
    echarts_option: { xAxis: { type: "category", data: labels }, yAxis: { type: "value" },
      legend: { show: names.length > 1, bottom: 0 }, series },
    visual_spec: { renderer: "safe-chart-wrapper", mark: "line",
      encoding: { x: { field: "period" }, y: { field: "value" }, color: { field: "metric" } },
      data: { values: previewLimit === undefined ? values : values.slice(0, previewLimit) },
    },
  }
}

it("retains all three full series when a saved preview cuts off the second and third", () => {
  const names = ["Average G", "Average AB", "Average R"]
  const chart = lineChart(938, names, 1000)
  render(<ChartsGrid charts={[chart]} />)
  const series = captured.option.series as { name: string; data: number[] }[]
  expect(series.map((item) => item.name)).toEqual(names)
  expect(series.map((item) => item.data.length)).toEqual([938, 938, 938])
  expect(series[1].data[937]).toBe(938)
  expect(series[2].data[937]).toBe(939)
})

it("retains a complete single line beyond the preview boundary", () => {
  render(<ChartsGrid charts={[lineChart(1200, ["Average score"], 1000)]} />)
  const series = captured.option.series as { data: number[] }[]
  expect(series[0].data).toHaveLength(1200)
  expect(series[0].data[1199]).toBe(1199)
})

it.each([undefined, "total"])("retains every supplied grouped or stacked value (%s)", (stack) => {
  const names = ["First group", "Second group"]
  const chart = lineChart(4, names)
  const categories = ["A", "B", "C", "D"]
  chart.type = "bar"
  chart.echarts_option = { xAxis: { type: "category", data: categories },
    yAxis: { type: "value" }, legend: { show: true }, series: names.map((name, index) => ({
      type: "bar", name, stack, data: categories.map((_, value) => value + index),
    })) }
  chart.visual_spec = { renderer: "safe-chart-wrapper", mark: "bar",
    encoding: { x: { field: "category" }, y: { field: "value", stack: stack === "total" ? "zero" : undefined },
      color: { field: "group" } }, data: { values: [
        { category: "A", group: names[0], value: 0 },
        { category: "B", group: names[0], value: 1 },
        { category: "C", group: names[0], value: 2 },
        { category: "D", group: names[0], value: 3 },
        { category: "A", group: names[1], value: 1 },
      ] },
  }
  render(<ChartsGrid charts={[chart]} />)
  const series = captured.option.series as { data: number[]; stack?: string }[]
  expect(series.map((item) => item.data)).toEqual([[0, 1, 2, 3], [1, 2, 3, 4]])
  expect(series.map((item) => item.stack)).toEqual([stack, stack])
})

it("keeps complete visual-spec conversion and its presentation settings", () => {
  const chart = lineChart(3, ["Average score"])
  render(<ChartsGrid charts={[chart]} />)
  const series = captured.option.series as { data: number[]; symbol: string }[]
  expect(series[0].data).toEqual([0, 1, 2])
  expect(series[0].symbol).toBe("none")
})

it.each([false, true])("guide labels preserve raw click values with a derived spec %s", (derived) => {
  const chart = lineChart(2, ["Amount"])
  chart.type = "bar"
  chart.yAxis = "status"
  chart.echarts_option = { _group_counts: { M: 3 },
    xAxis: { type: "value", name: "Amount" }, yAxis: { type: "category", data: ["M", "S"] },
    series: [{ type: "bar", name: "Amount", data: [10, 20] }],
    _reader_value_maps: { yAxis: { field: "status", values: [{ value: "M", label: "Married" }] } },
    _reader: { definitions: { status: { label: "Marital status", description: "Whether the person is married." } } },
  }
  chart.visual_spec = derived ? { renderer: "safe-chart-wrapper", mark: "bar",
    encoding: { x: { field: "amount", type: "quantitative", title: "Amount" }, y: { field: "status", type: "nominal" } },
    data: { values: [{ status: "M", amount: 10 }, { status: "S", amount: 20 }] },
  } : null
  render(<ChartsGrid charts={[chart]} />)
  const axis = captured.option.yAxis as { data: string[]; axisLabel: { formatter: (value: string) => string } }
  expect(axis.data).toEqual(["M", "S"])
  expect(axis.axisLabel.formatter("M")).toBe("Married (M)")
  expect(axis.axisLabel.formatter("S")).toBe("S")
  captured.toggleValue.mockClear()
  captured.onEvents.click?.({ name: "M" })
  expect(captured.toggleValue).toHaveBeenCalledWith("status", "M")
  const tooltip = captured.option.tooltip as { formatter: (items: { name: string; seriesName: string; value: number }[]) => string }
  const text = tooltip.formatter([{ name: "M", seriesName: "Amount", value: 10 }])
  expect(text).toContain("Married (M)")
  expect(text).toContain("3 entries with a supplied value")
  expect(screen.getByText("What these names mean")).toBeTruthy()
  expect(screen.getByText("Whether the person is married.")).toBeTruthy()
})

it.each(["M", ""])("guide meanings label pie legends while pie clicks retain the recorded code %s", (code) => {
  const meaning = code ? "Married" : "Other route"
  const display = code ? "Married (M)" : 'Other route ("")'
  const chart = lineChart(1, ["status"])
  chart.type = "donut"
  chart.visual_spec = null
  chart.echarts_option = { series: [{ type: "pie", data: [{ name: code, value: 2 }, { name: "Y", value: 3 }] }],
    _reader_value_maps: { pie: { field: "status", values: [{ value: code, label: meaning }] } },
  }
  render(<ChartsGrid charts={[chart]} />)
  const media = captured.option.media as { option: { legend: { formatter: (name: string) => string } } }[]
  expect(media[0].option.legend.formatter(code)).toContain(`${display}\n2`)
  expect((captured.option.series as { data: { name: string }[] }[])[0].data[0].name).toBe(code)
  if (code === "") {
    const legend = screen.getByRole("list", { name: "Chart categories" })
    expect(legend.textContent).toContain('Other route ("")')
    expect(legend.textContent).toContain("2 (40.0%)")
    expect(legend.textContent).toContain("Y")
    expect(legend.textContent).toContain("3 (60.0%)")
    expect((captured.option.legend as { show: boolean }).show).toBe(false)
  }
  captured.toggleValue.mockClear()
  captured.onEvents.click?.({ name: code })
  expect(captured.toggleValue).toHaveBeenCalledWith("status", code)
})
