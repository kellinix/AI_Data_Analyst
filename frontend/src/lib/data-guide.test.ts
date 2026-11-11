import { expect, it } from "vitest"
import { chartReaderDefinitions, chartReaderValueLabels, guideEntryValue, maximumDataGuideBytes, parseDataGuide, readDataGuide, readerLabel } from "./data-guide"

const guide = { version: 1, fields: [{ source_table: "people.csv", source_column: "status", label: "Marital status",
  values: [{ value: "M", label: "Married" }] }] }

it("reads a separate JSON guide including UTF-8 BOM", async () => {
  const parsed = await readDataGuide({ name: "source-guide.JSON", text: async () => `\uFEFF${JSON.stringify(guide)}` })
  expect(parsed).toEqual(guide)
  expect(await readDataGuide({ name: "source-guide", text: async () => JSON.stringify(guide) })).toEqual(guide)
})

it("rejects invalid guide files and bounds bytes before reading", async () => {
  let read = false
  await expect(readDataGuide({ name: "guide.csv", text: async () => "id,value\n1,2" })).rejects.toThrow("valid JSON guide")
  await expect(readDataGuide({ name: "guide.json", size: maximumDataGuideBytes + 1,
    text: async () => { read = true; return "" } })).rejects.toThrow("1 MB")
  expect(read).toBe(false)
  expect(() => parseDataGuide("{")).toThrow("valid JSON guide")
  expect(() => parseDataGuide(JSON.stringify({ version: 1, rows: [] }))).toThrow("field definitions")
  expect(() => parseDataGuide(JSON.stringify({ version: 1, fields: Array(201).fill(guide.fields[0]) }))).toThrow("200 fields")
  expect(() => parseDataGuide(JSON.stringify({ version: 1, fields: [{ source_column: "status" }] }))).toThrow("original file name")
  expect(() => parseDataGuide(JSON.stringify({ ...guide, fields: [{ ...guide.fields[0], values: Array(501).fill({ value: "M", label: "Married" }) }] }))).toThrow("500 codes")
})

it("bounds decoded UTF-8 bytes and rejects non-finite or structured code values", () => {
  expect(() => parseDataGuide(JSON.stringify({ ...guide, padding: "😀".repeat(300000) }))).toThrow("1 MB")
  expect(() => parseDataGuide('{"version":1,"fields":[{"source_table":"x.csv","source_column":"x","values":[{"value":1e999,"label":"x"}]}]}')).toThrow("finite numbers")
  expect(() => parseDataGuide(JSON.stringify({ ...guide, fields: [{ ...guide.fields[0], values: [{ value: {}, label: "x" }] }] }))).toThrow("simple value")
})

it("scopes display meanings to their bound fields and preserves original chart data", () => {
  const option = { xAxis: { type: "category", data: ["M", "m", "01"] }, yAxis: { type: "category", data: ["M"] },
    series: [{ name: "M", type: "pie", data: [{ name: "M", value: 2 }] }],
    _reader_value_maps: {
      xAxis: { field: "status", values: [{ value: "M", label: "Married" }, { value: "01", label: "First code" }] },
      yAxis: { field: "role", values: [{ value: "M", label: "Manager" }] },
      series: { field: "region", values: [{ value: "M", label: "Midlands" }] },
      pie: { field: "status", values: [{ value: "M", label: "Married" }] },
    } }
  const original = JSON.stringify(option)
  expect(chartReaderValueLabels(option)).toEqual({ xAxis: { M: "Married (M)", m: "m", "01": "First code (01)" },
    yAxis: { M: "Manager (M)" }, series: { M: "Midlands (M)" }, pie: { M: "Married (M)" } })
  expect(JSON.stringify(option)).toBe(original)
})

it("uses numeric binding only when supplied and retains original source-code spelling", () => {
  const labels = chartReaderValueLabels({ xAxis: { data: ["1", "1.0"] }, yAxis: { data: ["us"] },
    _reader_value_maps: { xAxis: { field: "flag", numeric: true, values: [{ value: 1, label: "Yes" }] },
      yAxis: { field: "country", values: [{ value: "us", raw_value: "US", label: "United States" }] },
    } })
  expect(labels.xAxis).toEqual({ "1": "Yes (1)", "1.0": "Yes (1.0)" })
  expect(labels.yAxis.us).toBe("United States (US)")
  expect(chartReaderValueLabels({ xAxis: { data: ["1.0"] }, _reader_value_maps: {
    xAxis: { field: "flag", numeric: true, values: [{ value: 1, raw_value: 1, label: "Yes", display_label: "Yes (1.0)" }] },
  } }).xAxis["1.0"]).toBe("Yes (1.0)")
  expect(chartReaderValueLabels({ xAxis: { data: ["01"] }, _reader_value_maps: {
    xAxis: { field: "identifier", numeric: false, values: [{ value: "1", label: "One" }] },
  } }).xAxis["01"]).toBe("01")
})

it("older charts have empty display maps and definitions", () => {
  expect(chartReaderValueLabels({ xAxis: { data: ["M"] } })).toEqual({ xAxis: {}, yAxis: {}, series: {}, pie: {} })
  expect(chartReaderDefinitions({})).toEqual([])
  expect(chartReaderDefinitions({ _reader: { definitions: { day: { label: "Submission day", description: "Day the work was sent.",
    unit: "days", time_basis: { kind: "relative_day", origin: "the course start" } } } } })).toEqual([
    { field: "day", label: "Submission day", description: "Day the work was sent.", unit: "days", origin: "the course start" },
  ])
})

it("treats reserved object-property names as ordinary recorded codes", () => {
  expect(readerLabel({}, "constructor")).toBe("constructor")
  const labels = chartReaderValueLabels({ yAxis: { data: ["__proto__"] }, _reader_value_maps: {
    yAxis: { field: "code", values: [{ value: "__proto__", label: "Special code" }] },
  } })
  expect(readerLabel(labels.yAxis, "__proto__")).toBe("Special code (__proto__)")
})

it("keeps text codes case- and type-specific while using server-projected display text", () => {
  const labels = chartReaderValueLabels({ xAxis: { data: [1, "1", "N", "n"] }, _reader_value_maps: {
    xAxis: { field: "code", numeric: false, values: [{ value: "1", label: "Text one" },
      { value: "N", label: "North" }, { value: "n", label: "Small n", display_label: "Small n (n)" }] },
  } })
  // ECharts text names cannot distinguish two differently typed codes with the same spelling.
  expect(labels.xAxis["1"]).toBe("1")
  expect(labels.xAxis.N).toBe("North (N)")
  expect(labels.xAxis.n).toBe("Small n (n)")
  expect(chartReaderValueLabels({ xAxis: { data: [1] }, _reader_value_maps: {
    xAxis: { field: "code", numeric: false, values: [{ value: "1", label: "Text one" }] },
  } }).xAxis["1"]).toBe("1")
})

it("entry display labels preserve raw values and exact numeric fallbacks", () => {
  const entry = { values: { code: "M", amount: 9007199254740991, constructor: "recorded" },
    display_values: { code: "Married (M)" } }
  expect(guideEntryValue(entry, "code")).toBe("Married (M)")
  expect(guideEntryValue(entry, "amount")).toBe(9007199254740991)
  expect(guideEntryValue(entry, "constructor")).toBe("recorded")
  expect(entry.values.code).toBe("M")
})

it("preserves large text codes and rejects rounded numeric code imports", () => {
  const first = "9007199254740992", second = "9007199254740993"
  expect(() => parseDataGuide('{"version":1,"fields":[{"source_table":"x.csv","source_column":"code","values":[{"value":9007199254740993,"label":"Second"}]}]}')).toThrow("too large to read exactly")
  expect(chartReaderValueLabels({ xAxis: { data: [first, second] }, _reader_value_maps: {
    xAxis: { field: "code", numeric: true, values: [{ value: first, label: "First" }, { value: second, label: "Second" }] },
  } }).xAxis).toEqual({ [first]: `First (${first})`, [second]: `Second (${second})` })
})
