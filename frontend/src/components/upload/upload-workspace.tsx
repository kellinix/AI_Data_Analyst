"use client"

import { useCallback, useState } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import {
  FileQuestion,
  FileSpreadsheet,
  GitMerge,
  Layers,
  Loader2,
  Network,
  Play,
  Sparkles,
  X,
} from "lucide-react"
import type { LucideIcon } from "lucide-react"
import { UploadZone } from "@/components/upload/upload-zone"
import { ProcessingAnimation } from "@/components/upload/processing-animation"
import { Button } from "@/components/ui/button"
import {
  useCreateAnalysis,
  useCreateCombinedAnalysis,
} from "@/hooks/use-analyses"
import { uploadsApi } from "@/lib/api/uploads"
import { cn, formatBytes } from "@/lib/utils"
import type { CleaningOptions, ColumnInfo, UploadedFile } from "@/types"

type UploadState = "idle" | "uploading" | "starting" | "processing"
type QueuedFile = {
  id: string
  file: File
  uploaded?: UploadedFile
  status: "queued" | "uploading" | "ready" | "starting" | "done" | "failed"
  error?: string
}

type RelationshipSuggestion = {
  id: string
  type: "join" | "stack" | "compare" | "separate" | "sheets"
  title: string
  description: string
  confidence: number
  columns: string[]
  files: string[]
}

function getErrorMessage(error: unknown): string {
  const maybeAxiosError = error as { code?: unknown } | null
  if (
    typeof error === "object" &&
    error !== null &&
    maybeAxiosError?.code === "ECONNABORTED"
  ) {
    return "The analysis setup is taking longer than expected. The file may still be processing; check the Analyses page or try again."
  }

  if (
    typeof error === "object" &&
    error !== null &&
    "response" in error &&
    typeof error.response === "object" &&
    error.response !== null &&
    "data" in error.response
  ) {
    const data = error.response.data as { detail?: unknown; error?: unknown }
    if (typeof data.detail === "string") return data.detail
    if (typeof data.error === "string") return data.error
  }

  if (error instanceof Error) return error.message
  return "Please try again or check the backend logs."
}

function normalizeColumnName(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
}

function getColumnNames(file: UploadedFile): string[] {
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

function generateRelationshipSuggestions(
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
            title: "Single dataset analysis",
            description:
              "Only one file was uploaded, so InsightFlow will analyse this dataset on its own.",
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

function suggestionIcon(type: RelationshipSuggestion["type"]): LucideIcon {
  if (type === "join") return GitMerge
  if (type === "stack") return Layers
  if (type === "compare") return Network
  if (type === "sheets") return FileSpreadsheet
  return FileQuestion
}

export function UploadWorkspace() {
  const router = useRouter()
  const [state, setState] = useState<UploadState>("idle")
  const [queuedFiles, setQueuedFiles] = useState<QueuedFile[]>([])
  const [dataDescription, setDataDescription] = useState("")
  const [instructions, setInstructions] = useState("")
  const [cleaningMode, setCleaningMode] = useState<CleaningOptions["mode"]>("clean")
  const [outlierPolicy, setOutlierPolicy] =
    useState<NonNullable<CleaningOptions["outlier_policy"]>>("cap")
  const [semanticCleanup, setSemanticCleanup] = useState(true)
  const [fuzzyDeduplicate, setFuzzyDeduplicate] = useState(false)
  const [processingStep, setProcessingStep] = useState(0)
  const createAnalysis = useCreateAnalysis()
  const createCombinedAnalysis = useCreateCombinedAnalysis()
  const uploadedFiles = queuedFiles
    .map((queued) => queued.uploaded)
    .filter((file): file is UploadedFile => Boolean(file))
  const hasUploadedProfiles =
    queuedFiles.length > 0 && queuedFiles.every((queued) => queued.uploaded)
  const relationshipSuggestions = generateRelationshipSuggestions(uploadedFiles)

  const handleFilesAccepted = useCallback((files: File[]) => {
    setQueuedFiles((current) => {
      const existing = new Set(
        current.map((item) => `${item.file.name}:${item.file.size}:${item.file.lastModified}`)
      )
      const additions = files
        .filter((file) => !existing.has(`${file.name}:${file.size}:${file.lastModified}`))
        .map((file) => ({
          id: `${file.name}-${file.size}-${file.lastModified}-${crypto.randomUUID()}`,
          file,
          status: "queued" as const,
        }))
      return [...current, ...additions]
    })
  }, [])

  const removeQueuedFile = useCallback((id: string) => {
    setQueuedFiles((current) => current.filter((item) => item.id !== id))
  }, [])

  const prepareFiles = useCallback(async () => {
    setState("uploading")

    try {
      for (const queued of queuedFiles) {
        if (queued.uploaded) continue

        setQueuedFiles((current) =>
          current.map((item) =>
            item.id === queued.id
              ? { ...item, status: "uploading", error: undefined }
              : item
          )
        )

        const uploaded = await uploadsApi.uploadFile(queued.file)

        setQueuedFiles((current) =>
          current.map((item) =>
            item.id === queued.id
              ? { ...item, uploaded, status: "ready" }
              : item
          )
        )
      }

      setState("idle")
      toast.success("Files profiled", {
        description: "Relationship suggestions are ready to review.",
      })
    } catch (error) {
      console.error("File upload or profiling failed", error)
      toast.error("Upload failed", {
        description: getErrorMessage(error),
      })
      setQueuedFiles((current) =>
        current.map((item) =>
          item.status === "uploading"
            ? { ...item, status: "failed", error: getErrorMessage(error) }
            : item
        )
      )
      setState("idle")
    }
  }, [queuedFiles])

  const startAnalyses = useCallback(
    async () => {
      if (queuedFiles.length === 0) return
      if (!hasUploadedProfiles) {
        await prepareFiles()
        return
      }
      setState("starting")

      try {
        const relationshipContext = {
          files: uploadedFiles.map((file) => ({
            id: file.id,
            name: file.original_filename,
            row_count: file.row_count,
            column_count: file.column_count,
            columns: getColumnNames(file),
          })),
          suggestions: relationshipSuggestions,
          data_description: dataDescription.trim() || null,
          instructions: instructions.trim() || null,
        }
        const cleaning: CleaningOptions = {
          mode: cleaningMode,
          remove_duplicates: true,
          fuzzy_deduplicate: fuzzyDeduplicate,
          standardize_columns: true,
          normalize_dates: true,
          clean_text: true,
          parse_currency_percent: true,
          drop_empty: true,
          missing_data_strategy: cleaningMode === "clean" ? "smart" : "none",
          outlier_policy: outlierPolicy,
          semantic_categorical_merging: semanticCleanup,
        }

        if (uploadedFiles.length > 1) {
          setQueuedFiles((current) =>
            current.map((item) => ({ ...item, status: "starting" }))
          )

          const analysis = await createCombinedAnalysis.mutateAsync({
            file_ids: uploadedFiles.map((file) => file.id),
            name: "Combined analysis",
            cleaning,
            relationship_context: {
              ...relationshipContext,
              analysis_mode: "combined",
              combine_strategy: "portfolio",
            },
          })

          setQueuedFiles((current) =>
            current.map((item) => ({ ...item, status: "done" }))
          )

          setState("processing")

          const steps = [0, 1, 2, 3, 4, 5, 6]
          for (const step of steps) {
            setProcessingStep(step)
            await new Promise((resolve) => setTimeout(resolve, 300))
          }

          router.push(`/analysis/${analysis.id}`)
          return
        }

        const queued = queuedFiles.find((item) => item.uploaded)
        if (!queued?.uploaded) return

        setQueuedFiles((current) =>
          current.map((item) =>
            item.id === queued.id ? { ...item, status: "starting" } : item
          )
        )

        const analysis = await createAnalysis.mutateAsync({
          file_id: queued.uploaded.id,
          name: queued.file.name.replace(/\.[^.]+$/, ""),
          cleaning,
          relationship_context: {
            ...relationshipContext,
            analysis_mode: "single",
            current_file_id: queued.uploaded.id,
            current_file_name: queued.uploaded.original_filename,
          },
        })

        setQueuedFiles((current) =>
          current.map((item) =>
            item.id === queued.id ? { ...item, status: "done" } : item
          )
        )

        setState("processing")

        const steps = [0, 1, 2, 3, 4, 5, 6]
        for (const step of steps) {
          setProcessingStep(step)
          await new Promise((resolve) => setTimeout(resolve, 300))
        }

        router.push(`/analysis/${analysis.id}`)
      } catch (error) {
        console.error("Upload or analysis creation failed", error)
        toast.error("Analysis did not start", {
          description: getErrorMessage(error),
        })
        setQueuedFiles((current) =>
          current.map((item) =>
            item.status === "uploading" || item.status === "starting"
              ? { ...item, status: "failed", error: getErrorMessage(error) }
              : item
          )
        )
        setState("idle")
      }
    },
    [
      createAnalysis,
      createCombinedAnalysis,
      dataDescription,
      cleaningMode,
      fuzzyDeduplicate,
      outlierPolicy,
      semanticCleanup,
      hasUploadedProfiles,
      instructions,
      prepareFiles,
      queuedFiles,
      relationshipSuggestions,
      router,
      uploadedFiles,
    ]
  )

  if (state === "processing") {
    return (
      <div className="flex min-h-[420px] items-center justify-center">
        <ProcessingAnimation step={processingStep} />
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <UploadZone
        onFilesAccepted={handleFilesAccepted}
        isUploading={state === "uploading"}
      />

      {queuedFiles.length > 0 && (
        <div className="rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
          <div className="flex items-center justify-between gap-4 border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
            <div>
              <h2 className="text-sm font-semibold text-zinc-900 dark:text-white">
                Files ready for analysis
              </h2>
              <p className="text-xs text-zinc-500">
                {queuedFiles.length} file{queuedFiles.length === 1 ? "" : "s"} selected
              </p>
            </div>
            <Button
              type="button"
              onClick={startAnalyses}
              disabled={state !== "idle" || queuedFiles.length === 0}
            >
              {state === "uploading" ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : state === "starting" ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              {state === "uploading"
                ? "Profiling files"
                : state === "starting"
                ? "Starting"
                : hasUploadedProfiles
                ? "Start analysis"
                : "Review relationships"}
            </Button>
          </div>

          <div className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {queuedFiles.map((queued) => (
              <div
                key={queued.id}
                className="flex items-center gap-3 px-4 py-3"
              >
                <div className="flex h-9 w-9 items-center justify-center rounded-md bg-zinc-100 dark:bg-zinc-900">
                  <FileSpreadsheet className="h-4 w-4 text-zinc-500" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-zinc-900 dark:text-white">
                    {queued.file.name}
                  </p>
                  <p className="text-xs text-zinc-500">
                    {formatBytes(queued.file.size)}
                    <span className="mx-1.5">/</span>
                    {queued.status}
                    {queued.error ? `: ${queued.error}` : ""}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => removeQueuedFile(queued.id)}
                  disabled={state !== "idle"}
                  className={cn(
                    "flex h-8 w-8 items-center justify-center rounded-md text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600 disabled:opacity-40 dark:hover:bg-zinc-900",
                    state !== "idle" && "cursor-not-allowed"
                  )}
                  aria-label={`Remove ${queued.file.name}`}
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {queuedFiles.length > 0 && (
        <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-md bg-emerald-50 text-emerald-600 dark:bg-emerald-950/40 dark:text-emerald-300">
                <Sparkles className="h-4 w-4" />
              </div>
              <div>
                <h2 className="text-sm font-semibold text-zinc-900 dark:text-white">
                  Data preparation
                </h2>
                <p className="text-xs text-zinc-500">
                  Missing values, duplicates, semantic category variants, messy dates, text, currency, percentages, and empty rows are handled before analysis.
                </p>
              </div>
            </div>

            <div className="grid grid-cols-2 rounded-lg border border-zinc-200 p-1 dark:border-zinc-800">
              {(["clean", "raw"] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setCleaningMode(mode)}
                  disabled={state !== "idle"}
                  className={cn(
                    "rounded-md px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50",
                    cleaningMode === mode
                      ? "bg-blue-600 text-white"
                      : "text-zinc-500 hover:text-zinc-900 dark:hover:text-white"
                  )}
                >
                  {mode === "clean" ? "Clean" : "Raw"}
                </button>
              ))}
            </div>
          </div>

          {cleaningMode === "clean" && (
            <div className="mt-4 grid gap-2 sm:grid-cols-2">
              <label className="flex items-center gap-3 rounded-lg border border-zinc-200 px-3 py-2 dark:border-zinc-800">
                <input
                  type="checkbox"
                  checked={semanticCleanup}
                  onChange={(event) => setSemanticCleanup(event.target.checked)}
                  disabled={state !== "idle"}
                  className="h-4 w-4 rounded border-zinc-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-zinc-700 dark:text-zinc-200">
                  Merge semantic category variants
                </span>
              </label>
              <label className="flex items-center gap-3 rounded-lg border border-zinc-200 px-3 py-2 dark:border-zinc-800">
                <input
                  type="checkbox"
                  checked={fuzzyDeduplicate}
                  onChange={(event) => setFuzzyDeduplicate(event.target.checked)}
                  disabled={state !== "idle"}
                  className="h-4 w-4 rounded border-zinc-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-zinc-700 dark:text-zinc-200">
                  Find near-duplicate text records
                </span>
              </label>
              <div className="rounded-lg border border-zinc-200 px-3 py-2 dark:border-zinc-800">
                <p className="mb-2 text-sm text-zinc-700 dark:text-zinc-200">
                  Outlier handling
                </p>
                <div className="grid grid-cols-3 gap-1 rounded-md bg-zinc-100 p-1 dark:bg-zinc-900">
                  {(["keep", "cap", "exclude"] as const).map((policy) => (
                    <button
                      key={policy}
                      type="button"
                      onClick={() => setOutlierPolicy(policy)}
                      disabled={state !== "idle"}
                      className={cn(
                        "rounded px-2 py-1 text-xs font-medium capitalize transition-colors disabled:opacity-50",
                        outlierPolicy === policy
                          ? "bg-blue-600 text-white"
                          : "text-zinc-500 hover:text-zinc-900 dark:hover:text-white"
                      )}
                    >
                      {policy}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {hasUploadedProfiles && (
        <div className="rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
          <div className="border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
            <h2 className="text-sm font-semibold text-zinc-900 dark:text-white">
              Automatic relationship suggestions
            </h2>
            <p className="mt-0.5 text-xs text-zinc-500">
              InsightFlow detected likely ways these files or sheets relate. Review them before starting analysis.
            </p>
          </div>

          <div className="space-y-3 p-4">
            {relationshipSuggestions.map((suggestion) => {
              const Icon = suggestionIcon(suggestion.type)
              return (
                <div
                  key={suggestion.id}
                  className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-800"
                >
                  <div className="flex items-start gap-3">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-blue-50 text-blue-600 dark:bg-blue-950/40 dark:text-blue-300">
                      <Icon className="h-4 w-4" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-3">
                        <h3 className="text-sm font-medium text-zinc-900 dark:text-white">
                          {suggestion.title}
                        </h3>
                        <span className="shrink-0 text-xs text-zinc-500">
                          {Math.round(suggestion.confidence * 100)}%
                        </span>
                      </div>
                      <p className="mt-1 text-xs leading-relaxed text-zinc-500">
                        {suggestion.description}
                      </p>
                      <p className="mt-2 truncate text-xs text-zinc-400">
                        Files: {suggestion.files.join(", ")}
                      </p>
                      {suggestion.columns.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {suggestion.columns.map((column) => (
                            <span
                              key={column}
                              className="rounded-md bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600 dark:bg-zinc-900 dark:text-zinc-300"
                            >
                              {column}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}

            <label className="block space-y-2">
              <span className="text-sm font-medium text-zinc-900 dark:text-white">
                What is this data about?
              </span>
              <textarea
                value={dataDescription}
                onChange={(event) => setDataDescription(event.target.value)}
                rows={3}
                placeholder="Optional: e.g. This is UK visa sponsorship COS volume data by organisation and visa route. Higher values mean more certificates assigned."
                className="w-full resize-none rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-900 outline-none transition-colors placeholder:text-zinc-400 focus:border-blue-500 dark:border-zinc-800 dark:bg-zinc-950 dark:text-white"
              />
            </label>

            <label className="block space-y-2">
              <span className="text-sm font-medium text-zinc-900 dark:text-white">
                Analysis instructions
              </span>
              <textarea
                value={instructions}
                onChange={(event) => setInstructions(event.target.value)}
                rows={4}
                placeholder="Optional: e.g. Join files by Organisation Name, compare 2025 vs 2026, and focus on COS volume changes."
                className="w-full resize-none rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-900 outline-none transition-colors placeholder:text-zinc-400 focus:border-blue-500 dark:border-zinc-800 dark:bg-zinc-950 dark:text-white"
              />
            </label>
          </div>
        </div>
      )}
    </div>
  )
}
