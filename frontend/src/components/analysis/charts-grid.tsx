"use client"

import dynamic from "next/dynamic"
import { motion } from "framer-motion"
import { useTheme } from "next-themes"
import { cn } from "@/lib/utils"
import { useFilterContext } from "@/contexts/filter-context"
import type { ChartConfig, DashboardPalette } from "@/types"
import { useDashboardContext } from "@/contexts/dashboard-context"
import { Button } from "@/components/ui/button"

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
          formatter: (params: { name: string; value: unknown; percent: number }) => `${params.name}\n${fullNumber(params.value, currency)} (${params.percent.toFixed(1)}%)`,
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
  const labelledSeries = seriesWithReadableLabels(chart, chartOption, horizontalBar, isDark, currency)
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

  const chartColors = CHART_PALETTES[palette]
  const option = {
    ...chartOption,
    color: [...chartColors.slice(index % chartColors.length), ...chartColors.slice(0, index % chartColors.length)],
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
      ...(yAxis._percentage ? { formatter: (params: { value: unknown }) => {
        const point = asArray(params.value)
        return `Grade average: ${fullNumber(point[0])}<br/>Recorded admission chance: ${fullNumber(Number(point[1]) * 100)}%`
      } } : {}),
    },
    legend: chartOption.legend ? {
      ...asObject(chartOption.legend),
      textStyle: { ...asObject(asObject(chartOption.legend).textStyle), color: axisText },
    } : undefined,
    xAxis: chartOption.xAxis
      ? {
          ...xAxis,
          name: xAxis._monthYearLabels ? "Month" : xAxis.name,
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
            formatter: (value: unknown) => compactNumber(value, currency),
            margin: 10,
            ...xAxisLabel,
            ...(xAxis._monthYearLabels ? { formatter: (value: unknown) => asObject(xAxis._monthYearLabels)[String(value)] ?? String(value) } : {}),
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
            formatter: horizontalBar ? undefined : (value: unknown) => compactNumber(value, currency),
            width: horizontalBar ? 230 : undefined,
            overflow: horizontalBar ? "truncate" : undefined,
            margin: horizontalBar ? 10 : 8,
            ...yAxisLabel,
            ...(yAxis._percentage ? { formatter: (value: number) => `${Math.round(value * 100)}%` } : {}),
          },
          // The stacked bars carry their own segment boundaries; gridlines
          // behind them read as extra divisions that aren't in the data.
          splitLine: { show: !stackedBar, lineStyle: { color: gridLine, type: "dashed" } },
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
      </div>
      <EChartsReact
        option={option}
        style={{ height: chart.type === "histogram" ? Math.max(340, asArray(yAxis.data).length * 34 + 100) : horizontalBar ? 340 : 320 }}
        opts={{ renderer: "svg" }}
        onEvents={{ click: handleChartClick }}
        lazyUpdate
      />
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
