"use client"

import dynamic from "next/dynamic"
import { motion } from "framer-motion"
import { useTheme } from "next-themes"
import { cn } from "@/lib/utils"
import { useFilterContext } from "@/contexts/filter-context"
import type { ChartConfig, DashboardPalette } from "@/types"
import { useDashboardContext } from "@/contexts/dashboard-context"
import { Button } from "@/components/ui/button"
import { chartReaderDefinitions, chartReaderValueLabels, readerLabel } from "@/lib/data-guide"

const EChartsReact = dynamic(() => import("echarts-for-react"), { ssr: false })

const CHART_PALETTES: Record<DashboardPalette, string[]> = {
  aurora: ["#7950E8", "#16B8A6", "#FF916B", "#E85BB6", "#E9B949", "#5B8DEF", "#8ACF61", "#9B7BE8"],
  sunset: ["#EF5D60", "#F49943", "#E9BA44", "#D554A8", "#9D65DF", "#F27477"],
  ocean: ["#1464C0", "#18A6BD", "#36C4A7", "#6687E6", "#5ED2D2", "#376CB2"],
  garden: ["#33875D", "#8AAD36", "#B4C44A", "#1F9B8D", "#6C9E51", "#A9B96C"],
}

interface ChartCardProps {
  chart: ChartConfig
  index: number
  palette: DashboardPalette
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

function plottedPointCount(option: Record<string, unknown>): number {
  return asArray(option.series).reduce<number>((total, item) =>
    total + asArray(asObject(item).data).filter((point) => point != null).length, 0)
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
          stack: asObject(encoding.y).stack === "zero" ? "total" : undefined,
          name: stack,
          emphasis: { focus: "series" },
          data: categories.map((category) => {
            const value = values.find(
                (row) => String(row[xField] ?? "") === category && String(row[stackField] ?? "") === stack
              )?.[yField]
            return value == null ? null : Number(value)
          }),
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
      _group_counts: chart.echarts_option._group_counts,
      _percentageValues: chart.echarts_option._percentageValues,
      grid: { left: horizontal ? 260 : 56, right: 28, top: 16, bottom: 44 },
      xAxis: horizontal
        ? { type: "value", name: xTitle }
        : { type: "category", name: xTitle, data: labels },
      yAxis: horizontal
        ? { type: "category", name: yTitle, data: labels, inverse: chart.type === "histogram", axisLabel: chart.type === "histogram" ? { interval: 0 } : undefined }
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
        boundaryGap: false,
        _monthYearLabels: asObject(asObject(chart.echarts_option).xAxis)._monthYearLabels,
        axisLabel: asObject(asObject(chart.echarts_option).xAxis).axisLabel,
        name: specTitle(encoding.x, axisLabel(chart, "xAxis") ?? chart.xAxis),
        data: labels,
      },
      yAxis: { type: "value", name: specTitle(encoding.y, axisLabel(chart, "yAxis") ?? chart.yAxis), min: asObject(asObject(chart.echarts_option).yAxis).min, scale: asObject(asObject(chart.echarts_option).yAxis).scale },
      series: groups.map((group) => ({
        type: "line",
        smooth: false,
        markPoint: asObject(asArray(asObject(chart.echarts_option).series).find((item) => asObject(item).name === group)).markPoint,
        symbol: "none",
        name: group,
        data: labels.map((label) => {
          const row = values.find(
            (candidate) =>
              String(candidate[xField] ?? "") === label &&
              (!colorField || String(candidate[colorField] ?? "Value") === group)
          )
          return row?.[yField] == null ? null : Number(row[yField])
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
    // The backend flags an axis spanning orders of magnitude; on a linear
    // scale those points all pile into one corner.
    const axisScale = (channel: unknown): string =>
      asObject(asObject(channel).scale).type === "log" ? "log" : "value"
    return {
      tooltip: { trigger: "item" },
      xAxis: {
        ...asObject(chart.echarts_option.xAxis),
        type: axisScale(encoding.x),
        name: specTitle(encoding.x, axisLabel(chart, "xAxis") ?? chart.xAxis),
      },
      yAxis: {
        ...asObject(chart.echarts_option.yAxis),
        type: axisScale(encoding.y),
        name: specTitle(encoding.y, axisLabel(chart, "yAxis") ?? chart.yAxis),
      },
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
  return (chart.type === "bar" || chart.type === "histogram") && yAxis.type === "category"
}

function seriesDataLength(series: Record<string, unknown>): number {
  return asArray(series.data).length
}


function seriesWithReadableLabels(
  chart: ChartConfig,
  option: Record<string, unknown>,
  horizontalBar: boolean,
  isDark: boolean,
  currency?: string | null,
  pieLabels: Record<string, string> = {}
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
          color: isDark ? "#e6def3" : "#6b6281",
          fontSize: 11,
          formatter: (params: { value: unknown; name: string }) => {
            const counts = asObject(option._group_counts)
            const count = counts[params.name]
            return `${fullNumber(params.value, currency)}${option._percentageValues ? "%" : ""}${count === undefined ? "" : ` (${count} ${count === 1 ? "record" : "records"})`}`
          },
        },
      }
    }

    if (type === "pie" || type === "donut") {
      return {
        ...series,
        label: {
          ...label,
          show: true,
          color: isDark ? "#e6def3" : "#615875",
          fontSize: 11,
          position: "outside",
          formatter: (params: { name: string; value: unknown; percent: number }) => `${readerLabel(pieLabels, params.name)}\n${fullNumber(params.value, currency)} (${params.percent.toFixed(1)}%)`,
        },
        labelLine: {
          show: true,
          length: 10,
          length2: 8,
          lineStyle: { color: isDark ? "#afa0c9" : "#a39bb7" },
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

function ChartCard({ chart, index, palette }: ChartCardProps) {
  const { resolvedTheme } = useTheme()
  const isDark = resolvedTheme === "dark"
  const axisText = isDark ? "#c9bedc" : "#706985"
  const axisLine = isDark ? "#574b6f" : "#e8e1f1"
  const gridLine = isDark ? "#433853" : "#ece7f3"
  const { chartPatches, activeFilters, toggleValue, isRefetching } = useFilterContext()
  const patch = chartPatches[chart.id]
  const effectiveChart: ChartConfig =
    patch && !patch.skipped
      ? { ...chart, visual_spec: patch.visual_spec ?? chart.visual_spec, echarts_option: patch.echarts_option,
          description: typeof asObject(patch.visual_spec).description === "string"
            ? String(asObject(patch.visual_spec).description) : chart.description }
      : chart

  const savedOption = asObject(effectiveChart.echarts_option)
  const visualOption = optionFromVisualSpec(effectiveChart)
  // Saved visual specs may contain only a bounded preview of the chart data.
  // Reconstructing a plot from that preview can drop periods or whole series.
  const chartOption = visualOption && plottedPointCount(visualOption) >= plottedPointCount(savedOption)
    ? visualOption : savedOption
  const readerLabels = chartReaderValueLabels({ ...chartOption, _reader_value_maps: savedOption._reader_value_maps })
  const definitions = chartReaderDefinitions(savedOption)
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
  const labelledSeries = seriesWithReadableLabels(chart, chartOption, horizontalBar, isDark, currency, readerLabels.pie)
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
    if (!filterColumn || params?.name == null) return
    toggleValue(filterColumn, params.name)
  }

  const chartColors = CHART_PALETTES[palette]
  const rotatedColors = [...chartColors.slice(index % chartColors.length), ...chartColors.slice(0, index % chartColors.length)]
  const visibleSeries = dimmedSeries ?? asArray(chartOption.series)
  const pieData = asArray(asObject(asArray(visibleSeries)[0]).data)
  const pieTotal = pieData.reduce<number>((total, item) => total + Number(asObject(item).value ?? 0), 0)
  // ECharts omits an empty-name legend item, even when that code has a meaning.
  const externalPieLegend = chart.type === "donut" && pieData.some((item) => asObject(item).name === "")
  const hasValueLabels = Object.values(readerLabels).some((labels) => Object.keys(labels).length > 0)
  type TooltipPoint = { name: string; seriesName?: string; value: unknown; percent?: number }
  function guideTooltip(parameters: TooltipPoint | TooltipPoint[]): string {
    const items = Array.isArray(parameters) ? parameters : [parameters]
    const first = items[0]
    if (!first) return ""
    if (chart.type === "donut") {
      return `${readerLabel(readerLabels.pie, first.name)}\n${fullNumber(first.value, currency)} (${Number(first.percent ?? 0).toFixed(1)}%)`
    }
    const categories = horizontalBar ? readerLabels.yAxis : readerLabels.xAxis
    const rows = items.map((item) => `${readerLabel(readerLabels.series, item.seriesName)} ${fullNumber(item.value, currency)}${chartOption._percentageValues ? "%" : ""}`.trim())
    const count = asObject(chartOption._group_counts)[first.name]
    if (count !== undefined) rows.push(`${count} entries with a supplied value`)
    return [readerLabel(categories, first.name), ...rows].join("\n")
  }
  const smallScreenOption = horizontalBar ? {
    grid: { left: 8, right: 56, top: 16, bottom: 60, containLabel: true },
    yAxis: { axisLabel: { width: 112, overflow: "break", lineHeight: 14, interval: 0, margin: 8 } },
    series: asArray(visibleSeries).map((item) => ({
      ...asObject(item),
      label: {
        ...asObject(asObject(item).label),
        fontSize: 10,
        formatter: (params: { value: unknown }) => `${compactNumber(params.value, currency)}${chartOption._percentageValues ? "%" : ""}`,
      },
    })),
  } : chart.type === "donut" ? {
    legend: {
      show: !externalPieLegend, selectedMode: false, left: 0, right: 0, bottom: 4,
      itemWidth: 10, itemHeight: 10, itemGap: 12,
      textStyle: { color: axisText, fontSize: 11, lineHeight: 16 },
      formatter: (name: string) => {
        const item = pieData.find((value) => asObject(value).name === name)
        const value = Number(asObject(item).value ?? 0)
        const percentage = pieTotal ? value / pieTotal * 100 : 0
        return `${readerLabel(readerLabels.pie, name)}\n${fullNumber(value, currency)} (${percentage.toFixed(1)}%)`
      },
    },
    series: asArray(visibleSeries).map((item) => ({
      ...asObject(item), center: externalPieLegend ? ["50%", "50%"] : ["50%", "32%"],
      radius: externalPieLegend ? ["28%", "55%"] : ["24%", "48%"],
      label: { show: false }, labelLine: { show: false },
    })),
  } : {}
  const option = {
    ...chartOption,
    color: rotatedColors,
    backgroundColor: "transparent",
    textStyle: {
      fontFamily: "Inter, system-ui, sans-serif",
      fontSize: 12,
      color: axisText,
    },
    animation: true,
    animationDuration: 600,
    animationEasing: "cubicOut",
    grid: {
      ...grid,
      top: 16,
      right: horizontalBar ? (chartOption._group_counts ? 156 : 84) : 28,
      bottom: horizontalBar ? 72 : chart.type === "histogram" ? 76 : 68,
      left: horizontalBar ? (chartOption._group_counts ? 64 : 260) : 64,
      containLabel: true,
    },
    tooltip: {
      trigger: horizontalBar ? "axis" : tooltip.trigger,
      backgroundColor: "#261d3f",
      borderColor: "#6d55a0",
      borderRadius: 12,
      padding: 12,
      textStyle: { color: "#fff", fontSize: 12 },
      ...tooltip,
      renderMode: "richText",
      confine: true,
      ...(horizontalBar && chartOption._group_counts ? { formatter: (params: { name: string; seriesName: string; value: unknown }[]) => {
        const first = params[0]
        if (!first) return ""
        const count = asObject(chartOption._group_counts)[first.name]
        return `${first.name}\n${first.seriesName} ${fullNumber(first.value, currency)}${chartOption._percentageValues ? "%" : ""}\n${count} entries with a supplied value`
      } } : {}),
      ...(yAxis._percentage ? { formatter: (params: { value: unknown }) => {
        const point = asArray(params.value)
        return `Grade average: ${fullNumber(point[0])}<br/>Recorded admission chance: ${fullNumber(Number(point[1]) * 100)}%`
      } } : {}),
      ...(hasValueLabels ? { formatter: guideTooltip } : {}),
    },
    legend: externalPieLegend ? { show: false } : chartOption.legend ? {
      ...asObject(chartOption.legend),
      textStyle: { ...asObject(asObject(chartOption.legend).textStyle), color: axisText },
      ...(Object.keys(readerLabels.series).length ? { formatter: (name: string) => readerLabel(readerLabels.series, name) } : {}),
    } : undefined,
    xAxis: chartOption.xAxis
      ? {
          ...xAxis,
          name: xAxis.name || (xAxis._monthYearLabels ? "Month" : undefined),
          nameLocation: "middle",
          nameGap: horizontalBar ? 44 : 48,
          nameTextStyle: {
            color: axisText,
            fontSize: 12,
            fontWeight: 600,
          },
          axisLine: { lineStyle: { color: axisLine } },
          axisTick: { show: false },
          axisLabel: {
            show: !hideXAxisTicks,
            color: axisText,
            hideOverlap: true,
            formatter: (value: unknown) => compactNumber(value, typeof xAxis._currency === "string" ? xAxis._currency : chart.type === "scatter" ? null : currency),
            margin: 10,
            ...xAxisLabel,
            ...(xAxis._monthYearLabels ? { formatter: (value: unknown) => asObject(xAxis._monthYearLabels)[String(value)] ?? String(value) } : {}),
            ...(Object.keys(readerLabels.xAxis).length ? { formatter: (value: unknown) => readerLabel(readerLabels.xAxis, value) } : {}),
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
            color: axisText,
            fontSize: 12,
            fontWeight: 600,
          },
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: {
            show: !hideYAxisTicks,
            color: axisText,
            hideOverlap: true,
            formatter: horizontalBar ? undefined : (value: unknown) => compactNumber(value, typeof yAxis._currency === "string" ? yAxis._currency : chart.type === "scatter" ? null : currency),
            width: horizontalBar ? 230 : undefined,
            overflow: horizontalBar ? "truncate" : undefined,
            margin: horizontalBar ? 10 : 8,
            ...yAxisLabel,
            ...(yAxis._percentage ? { formatter: (value: number) => `${Math.round(value * 100)}%` } : {}),
            ...(Object.keys(readerLabels.yAxis).length ? { formatter: (value: unknown) => readerLabel(readerLabels.yAxis, value) } : {}),
          },
          // The stacked bars carry their own segment boundaries; gridlines
          // behind them read as extra divisions that aren't in the data.
          splitLine: { show: !stackedBar, lineStyle: { color: gridLine, type: "dashed" } },
        }
      : undefined,
    series: externalPieLegend ? asArray(visibleSeries).map((item) => ({ ...asObject(item),
      center: ["50%", "50%"], radius: ["28%", "55%"], label: { show: false }, labelLine: { show: false },
    })) : dimmedSeries ?? chartOption.series,
    media: [{ query: { maxWidth: 480 }, option: smallScreenOption }],
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.07, duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      className={cn(
        "zephyr-card relative flex flex-col gap-4 overflow-hidden p-6 transition-all hover:shadow-lg dark:border-zinc-800 dark:bg-zinc-900/60",
        isRefetching && "opacity-70",
        filterColumn && "[&_canvas]:cursor-pointer [&_svg]:cursor-pointer"
      )}
    >
      <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-violet-500 via-teal-400 to-orange-400" />
      <div>
        <h3 className="text-base font-bold text-[#28203f] dark:text-white">
          {chart.title}
        </h3>
        {effectiveChart.description && (
          <p className="mt-1 text-sm text-zinc-500">{effectiveChart.description}</p>
        )}
        {definitions.length > 0 && <details className="mt-2 text-sm text-zinc-500">
          <summary className="cursor-pointer">What these names mean</summary>
          <p className="mt-2 text-xs">From the data guide supplied with this analysis.</p>
          <dl className="mt-2 space-y-3">{definitions.map((definition) => <div key={definition.field}>
            <dt className="font-medium text-zinc-700 dark:text-zinc-200">{definition.label}</dt>
            {definition.description && <dd>{definition.description}</dd>}
            {definition.unit && <dd>Measured in {definition.unit}.</dd>}
            {definition.origin && <dd>Days are counted from {definition.origin}.</dd>}
          </div>)}</dl>
        </details>}
      </div>
      <EChartsReact
        option={option}
        style={{ height: externalPieLegend ? 240 : horizontalBar ? Math.max(340, asArray(yAxis.data).length * 34 + 80) : 320 }}
        opts={{ renderer: "svg" }}
        onEvents={{ click: handleChartClick }}
        lazyUpdate
      />
      {externalPieLegend && <ul className="flex flex-wrap gap-x-4 gap-y-2 text-xs text-zinc-500" aria-label="Chart categories">
        {pieData.map((item, itemIndex) => {
          const value = asObject(item)
          const name = String(value.name ?? "")
          const amount = Number(value.value ?? 0)
          const color = asObject(value.itemStyle).color
          return <li key={`${name}-${itemIndex}`} className="flex max-w-full min-w-0 items-start gap-2">
            <span aria-hidden className="mt-1 h-2.5 w-2.5 shrink-0 rounded-sm" style={{
              backgroundColor: typeof color === "string" ? color : rotatedColors[itemIndex % rotatedColors.length],
            }} />
            <span className="min-w-0 break-words">{readerLabel(readerLabels.pie, name) || "Blank value"}<br />
              {fullNumber(amount, currency)} ({(pieTotal ? amount / pieTotal * 100 : 0).toFixed(1)}%)</span>
          </li>
        })}
      </ul>}
    </motion.div>
  )
}

interface ChartsGridProps {
  charts: ChartConfig[]
  analysisId?: string
}

export function ChartsGrid({ charts, analysisId }: ChartsGridProps) {
  const dashboard = useDashboardContext()
  const { layout, loading, saving, error, edit } = dashboard ?? {
    layout: null, loading: false, saving: false, error: null,
    edit: async () => {},
  }

  if (charts.length === 0) return null

  const byId = new Map(charts.map((chart) => [chart.id, chart]))
  const order = layout?.spec.chart_order ?? charts.map((chart) => chart.id)
  const hidden = new Set(layout?.spec.hidden_chart_ids ?? [])
  const visible = order.map((id) => byId.get(id)).filter((chart): chart is ChartConfig => chart !== undefined && !hidden.has(chart.id))
  const hiddenCharts = order.map((id) => byId.get(id)).filter((chart): chart is ChartConfig => chart !== undefined && hidden.has(chart.id))

  return (
    <section>
      <p className="zephyr-kicker mb-1">Visual exploration</p>
      <h2 className="mb-4 text-xl font-bold text-[#28203f] dark:text-white">
        Charts
      </h2>
      {analysisId && layout && (
        <div className="mb-4 flex flex-wrap items-center gap-2 text-xs text-zinc-500">
          <span>Saved layout · version {layout.version}</span>
          <Button size="sm" variant="ghost" disabled={saving || layout.version === 0}
            onClick={() => void edit("undo")}>Undo last change</Button>
          {hiddenCharts.map((chart) => (
            <Button key={chart.id} size="sm" variant="outline" disabled={saving}
              onClick={() => void edit("show", chart.id)}>Show {chart.title}</Button>
          ))}
        </div>
      )}
      {loading && <p className="mb-3 text-xs text-zinc-500">Loading saved layout…</p>}
      {error && <p role="alert" className="mb-3 text-xs text-amber-700">{error}</p>}
      <div className="grid gap-5 2xl:grid-cols-2">
        {visible.map((chart, i) => (
          <div key={chart.id} className="min-w-0">
            {analysisId && layout && (
              <div className="mb-1 flex justify-end gap-1">
                <label className="flex items-center gap-1 text-xs text-zinc-500 dark:text-zinc-400">
                  Colour
                  <select aria-label={`${chart.title} colour palette`}
                    className="rounded-md border border-zinc-200 bg-white px-2 py-1 text-xs text-zinc-800 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                    value={layout.spec.chart_palettes[chart.id] ?? "aurora"}
                    disabled={saving}
                    onChange={(event) => void edit("set_palette", chart.id, undefined, undefined, event.target.value as DashboardPalette)}>
                    <option value="aurora">Aurora</option>
                    <option value="sunset">Sunset</option>
                    <option value="ocean">Ocean</option>
                    <option value="garden">Garden</option>
                  </select>
                </label>
                <Button size="sm" variant="ghost" disabled={saving || i === 0}
                  onClick={() => void edit("move_up", chart.id)}>Move up</Button>
                <Button size="sm" variant="ghost" disabled={saving || i === visible.length - 1}
                  onClick={() => void edit("move_down", chart.id)}>Move down</Button>
                <Button size="sm" variant="ghost" disabled={saving}
                  onClick={() => void edit("hide", chart.id)}>Hide</Button>
              </div>
            )}
            <ChartCard chart={chart} index={i} palette={layout?.spec.chart_palettes[chart.id] ?? "aurora"} />
          </div>
        ))}
      </div>
      {visible.length === 0 && <p className="rounded-xl border border-dashed p-6 text-sm text-zinc-500">All charts are hidden. Use Show above to restore one.</p>}
    </section>
  )
}
