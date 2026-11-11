export const maximumDataGuideBytes = 1024 * 1024

export type DataGuide = {
  version: 1
  fields: Array<Record<string, unknown> & { source_table: string; source_column: string }>
}

type GuideFile = { name: string; size?: number; text: () => Promise<string> }

export function readerLabel(labels: Record<string, string>, value: unknown): string {
  const raw = String(value ?? "")
  return Object.prototype.hasOwnProperty.call(labels, raw) ? labels[raw] : raw
}

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
}

export function parseDataGuide(text: string): DataGuide {
  if (new TextEncoder().encode(text).byteLength > maximumDataGuideBytes) {
    throw new Error("Choose a data guide smaller than 1 MB.")
  }
  let guide: unknown
  let nonFinite = false
  try {
    guide = JSON.parse(text.replace(/^\uFEFF/, ""), (_key, value: unknown) => {
      if (typeof value === "number" && !Number.isFinite(value)) nonFinite = true
      return value
    })
  } catch {
    throw new Error("This data guide could not be read. Choose a valid JSON guide supplied with your data.")
  }
  if (nonFinite) throw new Error("A data guide can only contain finite numbers.")
  if (!isObject(guide) || guide.version !== 1 || !Array.isArray(guide.fields) || guide.fields.length === 0) {
    throw new Error("The data guide needs version 1 and a list of field definitions.")
  }
  if (guide.fields.length > 200) throw new Error("A data guide can define up to 200 fields.")
  for (const [index, field] of guide.fields.entries()) {
    if (!isObject(field) || typeof field.source_table !== "string" || !field.source_table ||
        typeof field.source_column !== "string" || !field.source_column) {
      throw new Error(`Definition ${index + 1} needs the original file name and column name.`)
    }
    if (field.values !== undefined && (!Array.isArray(field.values) || field.values.length > 500)) {
      throw new Error(`Definition ${index + 1} can explain up to 500 codes.`)
    }
    for (const entry of (field.values ?? []) as unknown[]) {
      if (!isObject(entry) || !("value" in entry) || typeof entry.label !== "string" || !entry.label ||
          (entry.value !== null && !["string", "number", "boolean"].includes(typeof entry.value)) ||
          (typeof entry.value === "number" && !Number.isFinite(entry.value))) {
        throw new Error(`Each code in definition ${index + 1} needs a simple value and its meaning.`)
      }
      if (typeof entry.value === "number" && Number.isInteger(entry.value) && !Number.isSafeInteger(entry.value)) {
        throw new Error("This guide contains a numeric code too large to read exactly. Ask the source for a guide with that code stored as text.")
      }
    }
  }
  return guide as DataGuide
}

export async function readDataGuide(file: GuideFile): Promise<DataGuide> {
  if (file.size !== undefined && file.size > maximumDataGuideBytes) {
    throw new Error("Choose a data guide smaller than 1 MB.")
  }
  return parseDataGuide(await file.text())
}

function valueLabel(binding: unknown, value: unknown): string {
  const raw = String(value ?? "")
  if (!isObject(binding) || !Array.isArray(binding.values)) return raw
  const exact = binding.values.find((entry: unknown) => isObject(entry) && entry.value === value)
  const definition = exact ?? binding.values.find((entry: unknown) => {
    if (!isObject(entry)) return false
    if (binding.numeric === true && typeof value !== "boolean" && typeof entry.value !== "boolean" &&
        value !== null && value !== "" && entry.value !== null && entry.value !== "") {
      const number = Number(value)
      const reference = Number(entry.value)
      if ((Number.isInteger(number) && !Number.isSafeInteger(number)) ||
          (Number.isInteger(reference) && !Number.isSafeInteger(reference))) return false
      if (Number.isFinite(number) && Number.isFinite(reference)) return number === reference
    }
    return entry.value === value
  })
  if (!isObject(definition) || typeof definition.label !== "string") return raw
  if (typeof definition.display_label === "string") return definition.display_label
  const original = "raw_value" in definition ? definition.raw_value : value
  const code = typeof original === "string" && original ? original : JSON.stringify(original) ?? raw
  return definition.label === code ? definition.label : `${definition.label} (${code})`
}

export function guideEntryValue(entry: { values: Record<string, unknown>; display_values?: Record<string, string> }, field: string): unknown {
  return entry.display_values && Object.prototype.hasOwnProperty.call(entry.display_values, field)
    ? entry.display_values[field] : entry.values[field]
}

function labelsForValues(binding: unknown, values: unknown[]): Record<string, string> {
  if (!binding) return {}
  const labels = new Map<string, string>()
  const ambiguous = new Set<string>()
  for (const value of values) {
    const raw = String(value ?? "")
    const label = valueLabel(binding, value)
    const previous = labels.get(raw)
    if (previous !== undefined && previous !== label) ambiguous.add(raw)
    labels.set(raw, label)
  }
  return Object.fromEntries([...labels].map(([raw, label]) => [raw, ambiguous.has(raw) ? raw : label]))
}

export function chartReaderDefinitions(option: Record<string, unknown>): Array<{
  field: string; label: string; description?: string; unit?: string; origin?: string
}> {
  const reader = isObject(option._reader) ? option._reader : {}
  const definitions = isObject(reader.definitions) ? reader.definitions : {}
  return Object.entries(definitions).flatMap(([field, definition]) => {
    if (!isObject(definition)) return []
    const basis = isObject(definition.time_basis) ? definition.time_basis : {}
    return [{ field, label: typeof definition.label === "string" ? definition.label : field,
      description: typeof definition.description === "string" ? definition.description : undefined,
      unit: typeof definition.unit === "string" ? definition.unit : undefined,
      origin: basis.kind === "relative_day" && typeof basis.origin === "string" ? basis.origin : undefined,
    }]
  })
}

/** Display-only labels leave the chart's original data and click values intact. */
export function chartReaderValueLabels(option: Record<string, unknown>): Record<string, Record<string, string>> {
  const bindings = isObject(option._reader_value_maps) ? option._reader_value_maps : {}
  const series = Array.isArray(option.series) ? option.series.filter(isObject) : []
  const xAxis = isObject(option.xAxis) ? option.xAxis : {}
  const yAxis = isObject(option.yAxis) ? option.yAxis : {}
  const pie = series.find((item) => item.type === "pie")
  const rawValues: Record<string, unknown[]> = {
    xAxis: Array.isArray(xAxis.data) ? xAxis.data : [],
    yAxis: Array.isArray(yAxis.data) ? yAxis.data : [],
    series: series.map((item) => item.name),
    pie: Array.isArray(pie?.data) ? pie.data.map((item: unknown) => isObject(item) ? item.name : item) : [],
  }
  return Object.fromEntries(Object.entries(rawValues).map(([target, values]) => [target,
    labelsForValues(bindings[target], values),
  ]))
}
