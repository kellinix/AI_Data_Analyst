"use client"

import dynamic from "next/dynamic"
import { motion } from "framer-motion"
import { cn } from "@/lib/utils"
import { useFilterContext } from "@/contexts/filter-context"
import type { ChartConfig } from "@/types"

const EChartsReact = dynamic(() => import("echarts-for-react"), { ssr: false })

const CHART_COLORS = [
  "#3b82f6", "#10b981", "#f59e0b", "#8b5cf6",
  "#ef4444", "#06b6d4", "#84cc16", "#f97316",
]

interface ChartCardProps {
  chart: ChartConfig
  index: number
}

function asObject(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function fieldName(channel: unknown): string | null {
  const channelObject = asObject(channel)
  const field = channelObject.field
  return typeof field === "string" ? field : null
}

function markType(spec: Record<string, unknown>): string {
  const mark = spec.mark
  if (typeof mark === "string") return mark
  const markObject = asObject(mark)
  return typeof markObject.type === "string" ? markObject.type : ""
}

function valuesFromSpec(spec: Record<string, unknown>): Record<string, unknown>[] {
  const data = asObject(spec.data)
  return asArray(data.values).filter(
    (item): item is Record<string, unknown> =>
      item !== null && typeof item === "object" && !Array.isArray(item)
  )
}

function specTitle(channel: unknown, fallback?: string | null): string {
  const channelObject = asObject(channel)
  return typeof channelObject.title === "string"
    ? channelObject.title
    : fallback ?? ""
}

/** The decoded axis label the backend put on the ECharts option, e.g.
 * "Financial Year Baseline (£m)" rather than the raw column name. Used as the
 * fallback when a spec encoding carries no title of its own. */
function axisLabel(chart: ChartConfig, axis: "xAxis" | "yAxis"): string | null {
  const name = asObject(asObject(chart.echarts_option)[axis]).name
  return typeof name === "string" && name.trim() ? name : null
}

function optionFromVisualSpec(chart: ChartConfig): Record<string, unknown> | null {
  const spec = asObject(chart.visual_spec)
  const renderer = spec.renderer
  if (renderer !== "safe-chart-wrapper") return null

  const values = valuesFromSpec(spec)
  const encoding = asObject(spec.encoding)
  const mark = markType(spec)

  if (mark === "bar") {
    const xField = fieldName(encoding.x)
    const yField = fieldName(encoding.y)
    if (!xField || !yField) return null

    // A colour encoding means the measure is split into stacked segments,
    // e.g. cost per department broken down by delivery status.
    const stackField = fieldName(encoding.color)
    if (stackField) {
      const categories = [...new Set(values.map((row) => String(row[xField] ?? "")))]
      const stacks = [...new Set(values.map((row) => String(row[stackField] ?? "")))]
      return {
        tooltip: { trigger: "axis" },
        legend: { show: true, bottom: 0 },
        grid: { left: 56, right: 28, top: 16, bottom: 56 },
        xAxis: { type: "category", name: specTitle(encoding.x, axisLabel(chart, "xAxis") ?? chart.xAxis), data: categories },
        yAxis: { type: "value", name: specTitle(encoding.y, axisLabel(chart, "yAxis") ?? chart.yAxis) },
        series: stacks.map((stack) => ({
          type: "bar",
          stack: "total",
          name: stack,
          emphasis: { focus: "series" },
          data: categories.map((category) =>
            Number(
              values.find(
                (row) => String(row[xField] ?? "") === category && String(row[stackField] ?? "") === stack
              )?.[yField] ?? 0
            )
          ),
        })),
      }
    }

    const xType = asObject(encoding.x).type
    const horizontal = xType === "quantitative"
    const categoryField = horizontal ? yField : xField
    const valueField = horizontal ? xField : yField
    const labels = values.map((row) => String(row[categoryField] ?? ""))
    const data = values.map((row) => Number(row[valueField] ?? 0))
    const xTitle = specTitle(encoding.x, axisLabel(chart, "xAxis") ?? chart.xAxis)
    const yTitle = specTitle(encoding.y, axisLabel(chart, "yAxis") ?? chart.yAxis)

    return {
      tooltip: { trigger: "axis" },
      grid: { left: horizontal ? 260 : 56, right: 28, top: 16, bottom: 44 },
      xAxis: horizontal
        ? { type: "value", name: xTitle }
        : { type: "category", name: xTitle, data: labels },
      yAxis: horizontal
        ? { type: "category", name: yTitle, data: labels }
        : { type: "value", name: yTitle },
      series: [
        {
          type: "bar",
          data,
          name: specTitle(horizontal ? encoding.x : encoding.y, chart.series[0]),
          itemStyle: { borderRadius: horizontal ? [0, 6, 6, 0] : [6, 6, 0, 0] },
        },
      ],
    }
  }

  if (mark === "line") {
    const xField = fieldName(encoding.x)
    const yField = fieldName(encoding.y)
    const colorField = fieldName(encoding.color)
    if (!xField || !yField) return null

    const labels = [...new Set(values.map((row) => String(row[xField] ?? "")))]
    const groups = colorField
      ? [...new Set(values.map((row) => String(row[colorField] ?? "Value")))]
      : ["Value"]
    return {
      tooltip: { trigger: "axis" },
      legend: { show: groups.length > 1, bottom: 0 },
      xAxis: {
        type: "category",
        name: specTitle(encoding.x, axisLabel(chart, "xAxis") ?? chart.xAxis),
        data: labels,
      },
      yAxis: { type: "value", name: specTitle(encoding.y, axisLabel(chart, "yAxis") ?? chart.yAxis) },
      series: groups.map((group) => ({
        type: "line",
        smooth: true,
        symbol: "none",
        name: group,
        data: labels.map((label) => {
          const row = values.find(
            (candidate) =>
              String(candidate[xField] ?? "") === label &&
              (!colorField || String(candidate[colorField] ?? "Value") === group)
          )
          return Number(row?.[yField] ?? 0)
        }),
      })),
    }
  }

  if (mark === "arc") {
    const thetaField = fieldName(encoding.theta)
    const colorField = fieldName(encoding.color)
    if (!thetaField || !colorField) return null
    return {
      tooltip: { trigger: "item" },
      series: [
        {
          type: "pie",
          radius: ["45%", "72%"],
          data: values.map((row) => ({
            name: String(row[colorField] ?? ""),
            value: Number(row[thetaField] ?? 0),
          })),
          itemStyle: { borderRadius: 8, borderWidth: 2, borderColor: "#fff" },
          label: { show: false },
        },
      ],
    }
  }

  if (mark === "point") {
    const xField = fieldName(encoding.x)
    const yField = fieldName(encoding.y)
    if (!xField || !yField) return null
    return {
      tooltip: { trigger: "item" },
      xAxis: { type: "value", name: specTitle(encoding.x, axisLabel(chart, "xAxis") ?? chart.xAxis) },
      yAxis: { type: "value", name: specTitle(encoding.y, axisLabel(chart, "yAxis") ?? chart.yAxis) },
      series: [
        {
          type: "scatter",
          symbolSize: 6,
          itemStyle: { opacity: 0.68 },
          data: values.map((row) => [Number(row[xField] ?? 0), Number(row[yField] ?? 0)]),
        },
      ],
    }
  }

  return null
}

/** Money charts carry the currency detected from the file, so an axis reads
 * "£117K" rather than "117K". Category labels pass through untouched. */
function currencyOptions(currency?: string | null): Intl.NumberFormatOptions {
  return currency ? { style: "currency", currency } : {}
}

function compactNumber(value: unknown, currency?: string | null): string {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return String(value ?? "")
  return new Intl.NumberFormat("en-US", {
    notation: Math.abs(numeric) >= 1000 ? "compact" : "standard",
    maximumFractionDigits: 1,
    ...currencyOptions(currency),
  }).format(numeric)
}

function fullNumber(value: unknown, currency?: string | null): string {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return String(value ?? "")
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: Number.isInteger(numeric) ? 0 : 2,
    ...currencyOptions(currency),
  }).format(numeric)
}

function isHorizontalBar(chart: ChartConfig, option: Record<string, unknown>) {
  const yAxis = asObject(option.yAxis)
  return chart.type === "bar" && yAxis.type === "category"
}

function seriesDataLength(series: Record<string, unknown>): number {
  return asArray(series.data).length
}

function labelValue(currency?: string | null) {
  return (params: { value: unknown }): string => {
    const value = Array.isArray(params.value) ? params.value[1] : params.value
    return fullNumber(value, currency)
  }
}

function seriesWithReadableLabels(
  chart: ChartConfig,
  option: Record<string, unknown>,
  horizontalBar: boolean,
  currency?: string | null
): unknown[] | undefined {
  const seriesItems = asArray(option.series)
  if (seriesItems.length === 0) return undefined

  return seriesItems.map((item) => {
    const series = asObject(item)
    const type = typeof series.type === "string" ? series.type : chart.type
    const label = asObject(series.label)
    const dataLength = seriesDataLength(series)

    // A stacked series labels the inside of its own segment, and a segment can
    // be a few pixels tall — four of them overprinted each other on the
    // cost-by-department-and-RAG chart. The tooltip carries those values.
    if (type === "bar" && !series.stack && dataLength <= 15) {
      return {
        ...series,
        label: {
          ...label,
          show: true,
          position: horizontalBar ? "right" : "top",
          color: "#a1a1aa",
          fontSize: 11,
          formatter: labelValue(currency),
        },
      }
    }

    if ((type === "pie" || type === "donut") && dataLength <= 8) {
      return {
        ...series,
        label: {
          ...label,
          show: true,
          color: "#d4d4d8",
          fontSize: 11,
          formatter: "{b}: {d}%",
        },
        labelLine: {
          show: true,
          length: 10,
          length2: 8,
          lineStyle: { color: "#71717a" },
        },
      }
    }

    return series
  })
}

/** The column a bar/donut chart's segments represent, for click-to-filter and
 * dimming — donut segments are keyed by `series[0]`, bars by `yAxis` (every
 * bar chart this app generates is horizontal with the category on the y
 * axis). Other chart types aren't filterable by click. */
function filterColumnForChart(chart: ChartConfig): string | null {
  if (chart.type === "donut") return chart.series[0] ?? null
  if (chart.type === "bar") return chart.yAxis
  return null
}

function categoryLabelsForChart(chart: ChartConfig, option: Record<string, unknown>, horizontalBar: boolean): string[] {
  if (chart.type === "donut") {
    const series = asArray(option.series)[0]
    return asArray(asObject(series).data).map((d) => String(asObject(d).name ?? ""))
  }
  if (chart.type === "bar") {
    const axis = horizontalBar ? asObject(option.yAxis) : asObject(option.xAxis)
    return asArray(axis.data).map(String)
  }
  return []
}

function seriesWithFilterDimming(
  chart: ChartConfig,
  series: unknown[] | undefined,
  categoryLabels: string[],
  activeValues: (string | number)[]
): unknown[] | undefined {
  if (!series || activeValues.length === 0) return series
  const activeStrings = activeValues.map(String)

  return series.map((item) => {
    const s = asObject(item)
    const type = typeof s.type === "string" ? s.type : chart.type

    if (type === "bar") {
      const data = asArray(s.data)
      return {
        ...s,
        data: data.map((value, i) => {
          const active = activeStrings.includes(categoryLabels[i])
          const existing = value && typeof value === "object" ? asObject(value) : { value }
          return { ...existing, itemStyle: { ...asObject(existing.itemStyle), opacity: active ? 1 : 0.3 } }
        }),
      }
    }

    if (type === "pie" || type === "donut") {
      const data = asArray(s.data)
      return {
        ...s,
        data: data.map((entry) => {
          const obj = asObject(entry)
          const active = activeStrings.includes(String(obj.name ?? ""))
          return { ...obj, itemStyle: { ...asObject(obj.itemStyle), opacity: active ? 1 : 0.3 } }
        }),
      }
    }

    return s
  })
}

function hasBarDataLabels(chart: ChartConfig, series: unknown[] | undefined): boolean {
  if (chart.type !== "bar" && chart.type !== "histogram") return false
  return (series ?? []).some((item) => {
    const s = asObject(item)
    const type = typeof s.type === "string" ? s.type : chart.type
    return type === "bar" && seriesDataLength(s) <= 15
  })
}

function ChartCard({ chart, index }: ChartCardProps) {
  const { chartPatches, activeFilters, toggleValue, isRefetching } = useFilterContext()
  const patch = chartPatches[chart.id]
  const effectiveChart: ChartConfig =
    patch && !patch.skipped
      ? { ...chart, visual_spec: patch.visual_spec ?? chart.visual_spec, echarts_option: patch.echarts_option }
      : chart

  const chartOption = optionFromVisualSpec(effectiveChart) ?? asObject(effectiveChart.echarts_option)
  const grid = asObject(chartOption.grid)
  const tooltip = asObject(chartOption.tooltip)
  const xAxis = asObject(chartOption.xAxis)
  const yAxis = asObject(chartOption.yAxis)
  const horizontalBar = isHorizontalBar(chart, chartOption)
  // Read off the series rather than the chart type: only a stacked bar sets it.
  const stackedBar = asArray(chartOption.series).some((item) => Boolean(asObject(item).stack))
  const xAxisLabel = asObject(xAxis.axisLabel)
  const yAxisLabel = asObject(yAxis.axisLabel)
  const currency = effectiveChart.currency ?? null
  const labelledSeries = seriesWithReadableLabels(chart, chartOption, horizontalBar, currency)
  // Each bar already shows its exact value via the data label added above —
  // the value axis's tick labels (0, 5, 10, ...) are redundant next to that,
  // not the category axis's labels, which are still the only way to tell
  // bars apart.
  const barLabelsShown = hasBarDataLabels(chart, labelledSeries)
  const hideXAxisTicks = barLabelsShown && horizontalBar
  const hideYAxisTicks = barLabelsShown && !horizontalBar

  const filterColumn = filterColumnForChart(chart)
  const activeValuesForThisChart =
    activeFilters.find((f) => f.column === filterColumn)?.values ?? []
  const categoryLabels = filterColumn
    ? categoryLabelsForChart(chart, chartOption, horizontalBar)
    : []
  const dimmedSeries = filterColumn
    ? seriesWithFilterDimming(
        chart,
        labelledSeries ?? asArray(chartOption.series),
        categoryLabels,
        activeValuesForThisChart
      )
    : labelledSeries

  function handleChartClick(params: { name?: string }) {
    if (!filterColumn || !params?.name) return
    toggleValue(filterColumn, params.name)
  }

  const option = {
    ...chartOption,
    color: CHART_COLORS,
    backgroundColor: "transparent",
    textStyle: {
      fontFamily: "Inter, system-ui, sans-serif",
      fontSize: 12,
    },
    animation: true,
    animationDuration: 600,
    animationEasing: "cubicOut",
    grid: {
      ...grid,
      top: 16,
      right: horizontalBar ? 84 : 28,
      bottom: horizontalBar ? 72 : chart.type === "histogram" ? 76 : 68,
      left: horizontalBar ? 260 : 64,
      containLabel: true,
    },
    tooltip: {
      trigger: horizontalBar ? "axis" : tooltip.trigger,
      backgroundColor: "rgba(0,0,0,0.8)",
      borderColor: "transparent",
      borderRadius: 8,
      textStyle: { color: "#fff", fontSize: 12 },
      ...tooltip,
    },
    xAxis: chartOption.xAxis
      ? {
          ...xAxis,
          nameLocation: "middle",
          nameGap: horizontalBar ? 44 : 48,
          nameTextStyle: {
            color: "#a1a1aa",
            fontSize: 12,
            fontWeight: 600,
          },
          axisLine: { lineStyle: { color: "#e4e4e7" } },
          axisTick: { show: false },
          axisLabel: {
            show: !hideXAxisTicks,
            color: "#71717a",
            hideOverlap: true,
            formatter: (value: unknown) => compactNumber(value, currency),
            margin: 10,
            ...xAxisLabel,
          },
          splitLine: { show: false },
        }
      : undefined,
    yAxis: chartOption.yAxis
      ? {
          ...yAxis,
          name: horizontalBar ? undefined : yAxis.name,
          nameLocation: "middle",
          nameGap: 52,
          nameTextStyle: {
            color: "#a1a1aa",
            fontSize: 12,
            fontWeight: 600,
          },
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: {
            show: !hideYAxisTicks,
            color: "#71717a",
            hideOverlap: true,
            formatter: horizontalBar ? undefined : (value: unknown) => compactNumber(value, currency),
            width: horizontalBar ? 230 : undefined,
            overflow: horizontalBar ? "truncate" : undefined,
            margin: horizontalBar ? 10 : 8,
            ...yAxisLabel,
          },
          // The stacked bars carry their own segment boundaries; gridlines
          // behind them read as extra divisions that aren't in the data.
          splitLine: { show: !stackedBar, lineStyle: { color: "#f4f4f5", type: "dashed" } },
        }
      : undefined,
    series: dimmedSeries ?? chartOption.series,
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.07, duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      className={cn(
        "flex flex-col gap-3 rounded-2xl border bg-white p-5 shadow-sm transition-opacity dark:border-zinc-800 dark:bg-zinc-900/60",
        isRefetching && "opacity-70",
        filterColumn && "[&_canvas]:cursor-pointer [&_svg]:cursor-pointer"
      )}
    >
      <div>
        <h3 className="text-sm font-semibold text-zinc-900 dark:text-white">
          {chart.title}
        </h3>
        {chart.description && (
          <p className="mt-0.5 text-xs text-zinc-500">{chart.description}</p>
        )}
      </div>
      <EChartsReact
        option={option}
        style={{ height: horizontalBar ? 340 : 320 }}
        opts={{ renderer: "svg" }}
        onEvents={{ click: handleChartClick }}
        lazyUpdate
      />
    </motion.div>
  )
}

interface ChartsGridProps {
  charts: ChartConfig[]
}

export function ChartsGrid({ charts }: ChartsGridProps) {
  if (charts.length === 0) return null

  return (
    <section>
      <h2 className="mb-4 text-base font-semibold text-zinc-900 dark:text-white">
        Charts
      </h2>
      <div className="grid gap-5 2xl:grid-cols-2">
        {charts.map((chart, i) => (
          <ChartCard key={chart.id} chart={chart} index={i} />
        ))}
      </div>
    </section>
  )
}
