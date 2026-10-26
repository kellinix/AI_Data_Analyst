import type { ChartConfig, DashboardAction, DashboardPalette, MetricDefinition } from "@/types"

export interface DashboardCommand {
  action: DashboardAction
  chartId?: string
  metricFamilyId?: string
  palette?: DashboardPalette
}

export function parseDashboardCommand(text: string, charts: ChartConfig[], metrics: MetricDefinition[]):
  { command: DashboardCommand | null; error: string | null } {
  const input = text.trim().replace(/[.!]+$/, "")
  if (/^undo dashboard$/i.test(input)) return { command: { action: "undo" }, error: null }
  if (/^save filters$/i.test(input)) return { command: { action: "save_filters" }, error: null }

  const paletteMatch = input.match(/^(?:color|colour) chart (.+) (aurora|sunset|ocean|garden)$/i)
  if (paletteMatch) {
    const title = paletteMatch[1].replace(/^["']|["']$/g, "").trim().toLocaleLowerCase()
    const matching = charts.filter((chart) => chart.title.toLocaleLowerCase() === title)
    if (matching.length !== 1) return { command: null, error: "Choose an exact chart title for the colour change." }
    return { command: { action: "set_palette", chartId: matching[0].id,
      palette: paletteMatch[2].toLocaleLowerCase() as DashboardPalette }, error: null }
  }

  const chartMatch = input.match(/^(hide|show|move) chart (.+)$/i)
  if (chartMatch) {
    const [, verb, raw] = chartMatch
    const direction = raw.match(/ (up|down)$/i)?.[1]
    const rawTitle = direction && verb.toLowerCase() === "move" ? raw.slice(0, -(direction.length + 1)) : raw
    const title = rawTitle.replace(/^["']|["']$/g, "").trim().toLocaleLowerCase()
    const matching = charts.filter((chart) => chart.title.toLocaleLowerCase() === title)
    if (matching.length !== 1) return { command: null, error: `Choose an exact chart title. Found ${matching.length} matches for “${rawTitle}”.` }
    if (verb.toLowerCase() === "move" && !direction) return { command: null, error: "Add up or down after the chart title." }
    const action = verb.toLowerCase() === "move"
      ? (direction?.toLowerCase() === "up" ? "move_up" : "move_down")
      : verb.toLowerCase() as "hide" | "show"
    return { command: { action, chartId: matching[0].id }, error: null }
  }

  const metricMatch = input.match(/^(pin|unpin) metric (.+)$/i)
  if (metricMatch) {
    const [, verb, rawName] = metricMatch
    const name = rawName.replace(/^["']|["']$/g, "").trim().toLocaleLowerCase()
    const matching = metrics.filter((metric) => metric.name.toLocaleLowerCase() === name)
    if (matching.length !== 1) return { command: null, error: `Choose an exact approved metric name. Found ${matching.length} matches for “${rawName}”.` }
    return { command: { action: verb.toLowerCase() === "pin" ? "pin_metric" : "unpin_metric",
      metricFamilyId: matching[0].family_id }, error: null }
  }

  if (/^(?:(?:hide|show|move|color|colour) chart|(?:pin|unpin) metric|undo dashboard|save filters)\b/i.test(input)) {
    return { command: null, error: "Try: hide chart \"Title\", colour chart \"Title\" ocean, pin metric \"Name\", save filters, or undo dashboard." }
  }
  return { command: null, error: null }
}
