"use client"

import dynamic from "next/dynamic"
import { motion } from "framer-motion"
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

    const xType = asObject(encoding.x).type
    const horizontal = xType === "quantitative"
    const categoryField = horizontal ? yField : xField
    const valueField = horizontal ? xField : yField
    const labels = values.map((row) => String(row[categoryField] ?? ""))
    const data = values.map((row) => Number(row[valueField] ?? 0))

    return {
      tooltip: { trigger: "axis" },
      grid: { left: horizontal ? 260 : 56, right: 28, top: 16, bottom: 44 },
      xAxis: horizontal
        ? { type: "value", name: specTitle(encoding.x, chart.xAxis) }
        : { type: "category", name: specTitle(encoding.x, chart.xAxis), data: labels },
      yAxis: horizontal
        ? { type: "category", name: specTitle(encoding.y, chart.yAxis), data: labels }
        : { type: "value", name: specTitle(encoding.y, chart.yAxis) },
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
      xAxis: { type: "category", name: specTitle(encoding.x, chart.xAxis), data: labels },
      yAxis: { type: "value", name: specTitle(encoding.y, chart.yAxis) },
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
      xAxis: { type: "value", name: specTitle(encoding.x, chart.xAxis) },
      yAxis: { type: "value", name: specTitle(encoding.y, chart.yAxis) },
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

function compactNumber(value: unknown): string {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return String(value ?? "")
  return new Intl.NumberFormat("en-US", {
    notation: Math.abs(numeric) >= 1000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(numeric)
}

function fullNumber(value: unknown): string {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return String(value ?? "")
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: Number.isInteger(numeric) ? 0 : 2,
  }).format(numeric)
}

function isHorizontalBar(chart: ChartConfig, option: Record<string, unknown>) {
  const yAxis = asObject(option.yAxis)
  return chart.type === "bar" && yAxis.type === "category"
}

function seriesDataLength(series: Record<string, unknown>): number {
  return asArray(series.data).length
}

function labelValue(params: { value: unknown }): string {
  const value = Array.isArray(params.value) ? params.value[1] : params.value
  return fullNumber(value)
}

function seriesWithReadableLabels(
  chart: ChartConfig,
  option: Record<string, unknown>,
  horizontalBar: boolean
): unknown[] | undefined {
  const seriesItems = asArray(option.series)
  if (seriesItems.length === 0) return undefined

  return seriesItems.map((item) => {
    const series = asObject(item)
    const type = typeof series.type === "string" ? series.type : chart.type
    const label = asObject(series.label)
    const dataLength = seriesDataLength(series)

    if (type === "bar" && dataLength <= 15) {
      return {
        ...series,
        label: {
          ...label,
          show: true,
          position: horizontalBar ? "right" : "top",
          color: "#a1a1aa",
          fontSize: 11,
          formatter: labelValue,
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

function ChartCard({ chart, index }: ChartCardProps) {
  const chartOption = optionFromVisualSpec(chart) ?? asObject(chart.echarts_option)
  const grid = asObject(chartOption.grid)
  const tooltip = asObject(chartOption.tooltip)
  const xAxis = asObject(chartOption.xAxis)
  const yAxis = asObject(chartOption.yAxis)
  const horizontalBar = isHorizontalBar(chart, chartOption)
  const xAxisLabel = asObject(xAxis.axisLabel)
  const yAxisLabel = asObject(yAxis.axisLabel)
  const labelledSeries = seriesWithReadableLabels(chart, chartOption, horizontalBar)

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
            color: "#71717a",
            hideOverlap: true,
            formatter: compactNumber,
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
            color: "#71717a",
            hideOverlap: true,
            formatter: horizontalBar ? undefined : compactNumber,
            width: horizontalBar ? 230 : undefined,
            overflow: horizontalBar ? "truncate" : undefined,
            margin: horizontalBar ? 10 : 8,
            ...yAxisLabel,
          },
          splitLine: { lineStyle: { color: "#f4f4f5", type: "dashed" } },
        }
      : undefined,
    series: labelledSeries ?? chartOption.series,
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.07, duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      className="flex flex-col gap-3 rounded-2xl border bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/60"
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
