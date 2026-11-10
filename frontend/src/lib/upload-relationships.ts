import type { ColumnInfo, UploadedFile } from "@/types"

export type RelationshipSuggestion = {
  id: string
  type: "join" | "stack" | "compare" | "separate" | "sheets"
  title: string
  description: string
  confidence: number
  columns: string[]
  files: string[]
}

function normalizeColumnName(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
}

export function getColumnNames(file: UploadedFile): string[] {
  return (file.columns ?? []).map((column) => column.name).filter(Boolean)
}

function getColumnByNormalizedName(
  file: UploadedFile,
  normalizedName: string
): ColumnInfo | undefined {
  return (file.columns ?? []).find(
    (column) => normalizeColumnName(column.name) === normalizedName
  )
}

function getYear(value: string): string | null {
  return value.match(/\b(20\d{2}|19\d{2})\b/)?.[1] ?? null
}

function isWeakJoinColumn(normalizedName: string): boolean {
  const weakColumns = new Set([
    "year",
    "month",
    "quarter",
    "date",
    "created_at",
    "updated_at",
    "description",
    "summary",
    "title",
    "headline",
    "is_real_headline",
  ])

  return (
    weakColumns.has(normalizedName) ||
    normalizedName.endsWith("_date") ||
    normalizedName.startsWith("is_") ||
    normalizedName.includes("description")
  )
}

function isLikelyJoinKey(normalizedName: string, column?: ColumnInfo): boolean {
  if (isWeakJoinColumn(normalizedName)) return false

  const nameSignals = [
    "id",
    "code",
    "name",
    "company",
    "organisation",
    "organization",
    "sponsor",
    "manufacturer",
  ]
  const hasNameSignal = nameSignals.some(
    (signal) =>
      normalizedName === signal ||
      normalizedName.endsWith(`_${signal}`) ||
      normalizedName.includes(`${signal}_`) ||
      normalizedName.includes(signal)
  )
  if (!hasNameSignal) return false

  if (!column) return true
  const nonNullCount = Math.max(column.non_null_count ?? 0, 1)
  const uniqueness = (column.unique_count ?? 0) / nonNullCount
  return normalizedName.includes("id") || uniqueness >= 0.1
}

function comparisonColumns(
  sharedKeys: string[],
  sharedColumns: string[]
): string[] {
  const preferred = sharedKeys
    .map((key, index) => ({ key, column: sharedColumns[index] }))
    .filter(({ key }) => key === "year" || key.includes("area") || key.includes("type"))
    .map(({ column }) => column)

  return preferred.length > 0 ? preferred : sharedColumns
}

export function generateRelationshipSuggestions(
  files: UploadedFile[]
): RelationshipSuggestion[] {
  if (files.length === 0) return []

  const suggestions: RelationshipSuggestion[] = []

  for (const file of files) {
    const columnNames = getColumnNames(file)
    const hasSheetColumn = columnNames.some(
      (column) => normalizeColumnName(column) === "sheet"
    )
    if (hasSheetColumn) {
      suggestions.push({
        id: `sheets:${file.id}`,
        type: "sheets",
        title: "Workbook sheets detected",
        description:
          "This file includes a Sheet column, so multiple sheets were probably combined during profiling.",
        confidence: 0.82,
        columns: ["Sheet"],
        files: [file.original_filename],
      })
    }
  }

  if (files.length === 1) {
    return suggestions.length > 0
      ? suggestions
      : [
          {
            id: `single:${files[0].id}`,
            type: "separate",
            title: "Single file analysis",
            description:
              "Only one file was uploaded, so Vesquiri will analyse it on its own.",
            confidence: 1,
            columns: [],
            files: [files[0].original_filename],
          },
        ]
  }

  const fileProfiles = files.map((file) => {
    const columns = getColumnNames(file)
    const normalized = new Map(
      columns.map((column) => [normalizeColumnName(column), column])
    )
    return { file, columns, normalized }
  })

  for (let i = 0; i < fileProfiles.length; i += 1) {
    for (let j = i + 1; j < fileProfiles.length; j += 1) {
      const left = fileProfiles[i]
      const right = fileProfiles[j]
      const sharedKeys = [...left.normalized.keys()].filter((key) =>
        right.normalized.has(key)
      )
      const sharedColumns = sharedKeys.map((key) => left.normalized.get(key)!)
      const strongJoinColumns = sharedKeys
        .filter((key) =>
          isLikelyJoinKey(key, getColumnByNormalizedName(left.file, key))
        )
        .map((key) => left.normalized.get(key)!)
      const compareColumns = comparisonColumns(sharedKeys, sharedColumns)
      const leftColumnCount = Math.max(left.normalized.size, 1)
      const rightColumnCount = Math.max(right.normalized.size, 1)
      const overlap =
        sharedKeys.length / Math.min(leftColumnCount, rightColumnCount)
      const leftYear = getYear(left.file.original_filename)
      const rightYear = getYear(right.file.original_filename)

      if (overlap >= 0.8) {
        suggestions.push({
          id: `stack:${left.file.id}:${right.file.id}`,
          type: "stack",
          title: "Stack files with matching structure",
          description:
            "These files have very similar columns, so they may represent the same report from different periods or sources.",
          confidence: Math.min(0.95, overlap),
          columns: sharedColumns.slice(0, 6),
          files: [left.file.original_filename, right.file.original_filename],
        })
      } else if (sharedKeys.length > 0) {
        if (strongJoinColumns.length > 0) {
          suggestions.push({
            id: `join:${left.file.id}:${right.file.id}`,
            type: "join",
            title: `Join by ${strongJoinColumns.slice(0, 2).join(" and ")}`,
            description:
              "These files share identifier-like columns that may connect related records.",
            confidence: Math.min(0.9, 0.55 + strongJoinColumns.length * 0.12),
            columns: strongJoinColumns.slice(0, 6),
            files: [left.file.original_filename, right.file.original_filename],
          })
        } else {
          suggestions.push({
            id: `compare-shared:${left.file.id}:${right.file.id}`,
            type: "compare",
            title: `Compare by ${compareColumns.slice(0, 2).join(" and ")}`,
            description:
              "These files share context columns, but not strong record identifiers, so comparison is safer than joining.",
            confidence: Math.min(0.82, 0.48 + sharedKeys.length * 0.08),
            columns: compareColumns.slice(0, 6),
            files: [left.file.original_filename, right.file.original_filename],
          })
        }
      }

      if (leftYear && rightYear && leftYear !== rightYear && sharedKeys.length > 0) {
        suggestions.push({
          id: `compare:${left.file.id}:${right.file.id}`,
          type: "compare",
          title: `Compare ${leftYear} vs ${rightYear}`,
          description:
            "The filenames look like different years with shared columns, so year-over-year comparison may be useful.",
          confidence: 0.86,
          columns: sharedColumns.slice(0, 6),
          files: [left.file.original_filename, right.file.original_filename],
        })
      }
    }
  }

  if (suggestions.length === 0) {
    suggestions.push({
      id: "separate",
      type: "separate",
      title: "Analyse files separately",
      description:
        "No strong shared columns were detected, so separate analyses are likely safest.",
      confidence: 0.78,
      columns: [],
      files: files.map((file) => file.original_filename),
    })
  }

  return suggestions
    .sort((a, b) => b.confidence - a.confidence)
    .slice(0, 5)
}

