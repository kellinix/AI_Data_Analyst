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
import type { CleaningOptions, UploadedFile } from "@/types"
import { readDataGuide, type DataGuide } from "@/lib/data-guide"
import {
  generateRelationshipSuggestions,
  getColumnNames,
  type RelationshipSuggestion,
} from "@/lib/upload-relationships"

type UploadState = "idle" | "uploading" | "starting" | "processing"
type QueuedFile = {
  id: string
  file: File
  uploaded?: UploadedFile
  status: "queued" | "uploading" | "ready" | "starting" | "done" | "failed"
  error?: string
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
    if (Array.isArray(data.detail)) {
      const messages = data.detail.flatMap((item) =>
        item && typeof item === "object" && "msg" in item && typeof item.msg === "string" ? [item.msg] : [])
      if (messages.length) return messages.slice(0, 3).join(". ")
    }
    if (typeof data.error === "string") return data.error
  }

  if (error instanceof Error) return error.message
  return "Something went wrong. Please try again."
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
  const [guide, setGuide] = useState<{ name: string; data?: DataGuide; error?: string } | null>(null)
  const [guideLoading, setGuideLoading] = useState(false)
  const [cleaningMode, setCleaningMode] = useState<CleaningOptions["mode"]>("clean")
  const [outlierPolicy, setOutlierPolicy] =
    useState<NonNullable<CleaningOptions["outlier_policy"]>>("keep")
  const [semanticCleanup, setSemanticCleanup] = useState(false)
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

  async function chooseGuide(file: File | undefined) {
    if (!file) return
    setGuideLoading(true)
    setGuide({ name: file.name })
    try {
      setGuide({ name: file.name, data: await readDataGuide(file) })
    } catch (error) {
      setGuide({ name: file.name, error: getErrorMessage(error) })
    } finally {
      setGuideLoading(false)
    }
  }

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
      if (queuedFiles.length === 0 || guideLoading || guide?.error) return
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
          ...(guide?.data ? { data_dictionary: guide.data } : {}),
        }
        const cleaning: CleaningOptions = {
          mode: cleaningMode,
          remove_duplicates: false,
          fuzzy_deduplicate: fuzzyDeduplicate,
          standardize_columns: true,
          normalize_dates: true,
          clean_text: true,
          parse_currency_percent: true,
          drop_empty: true,
          missing_data_strategy: "none",
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
      guide,
      guideLoading,
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

      <div className="space-y-2 rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
        <label htmlFor="data-guide-file" className="block text-sm font-semibold text-zinc-900 dark:text-white">Data guide (optional)</label>
        <p className="text-xs text-zinc-500">Choose the JSON guide supplied with your data to explain column names and codes. Up to 1 MB.</p>
        <input id="data-guide-file" type="file" accept=".json,application/json" disabled={state !== "idle" || guideLoading}
          className="block max-w-full text-sm" onChange={(event) => {
            const file = event.currentTarget.files?.[0]
            event.currentTarget.value = ""
            void chooseGuide(file)
          }} />
        {guideLoading && <p className="text-sm text-zinc-500">Reading data guide…</p>}
        {guide && <div className="flex flex-wrap items-center gap-3 text-sm">
          <span className="break-all">{guide.name}{guide.data ? ` · ${guide.data.fields.length} field definition${guide.data.fields.length === 1 ? "" : "s"}` : ""}</span>
          <Button type="button" variant="ghost" disabled={state !== "idle" || guideLoading} onClick={() => setGuide(null)}>Remove data guide</Button>
        </div>}
        {guide?.error && <p role="alert" className="text-sm text-red-600">{guide.error}</p>}
      </div>

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
              disabled={state !== "idle" || queuedFiles.length === 0 || guideLoading || !!guide?.error}
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
                  Tidy dates, text, currency, and percentages. Missing amounts and repeated records stay as supplied. Category merging and duplicate removal are optional.
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
              <label className="flex items-start gap-3 rounded-lg border border-zinc-200 px-3 py-2 dark:border-zinc-800">
                <input
                  type="checkbox"
                  checked={semanticCleanup}
                  onChange={(event) => setSemanticCleanup(event.target.checked)}
                  disabled={state !== "idle"}
                  className="mt-0.5 h-4 w-4 rounded border-zinc-300 text-blue-600 focus:ring-blue-500"
                />
                <span>
                  <span className="block text-sm text-zinc-700 dark:text-zinc-200">
                    Merge similar categories
                  </span>
                  <span className="block text-xs text-zinc-400">
                    e.g. treats &quot;USA&quot;, &quot;US&quot;, and &quot;United States&quot; as one value
                  </span>
                </span>
              </label>
              <label className="flex items-start gap-3 rounded-lg border border-zinc-200 px-3 py-2 dark:border-zinc-800">
                <input
                  type="checkbox"
                  checked={fuzzyDeduplicate}
                  onChange={(event) => setFuzzyDeduplicate(event.target.checked)}
                  disabled={state !== "idle"}
                  className="mt-0.5 h-4 w-4 rounded border-zinc-300 text-blue-600 focus:ring-blue-500"
                />
                <span>
                  <span className="block text-sm text-zinc-700 dark:text-zinc-200">
                    Find near-duplicate rows
                  </span>
                  <span className="block text-xs text-zinc-400">
                    Catches rows that are almost identical, like a repeat entry with a typo
                  </span>
                </span>
              </label>
              <div className="rounded-lg border border-zinc-200 px-3 py-2 dark:border-zinc-800 sm:col-span-2">
                <p className="text-sm text-zinc-700 dark:text-zinc-200">
                  Unusually high or low values
                </p>
                <p className="mb-2 text-xs text-zinc-400">
                  How to handle numbers far outside the normal range for a column (often data entry mistakes)
                </p>
                <div className="grid grid-cols-3 gap-1 rounded-md bg-zinc-100 p-1 dark:bg-zinc-900">
                  {(
                    [
                      { value: "keep", label: "Keep them" },
                      { value: "cap", label: "Smooth them" },
                      { value: "exclude", label: "Remove them" },
                    ] as const
                  ).map((policy) => (
                    <button
                      key={policy.value}
                      type="button"
                      onClick={() => setOutlierPolicy(policy.value)}
                      disabled={state !== "idle"}
                      className={cn(
                        "rounded px-2 py-1 text-xs font-medium transition-colors disabled:opacity-50",
                        outlierPolicy === policy.value
                          ? "bg-blue-600 text-white"
                          : "text-zinc-500 hover:text-zinc-900 dark:hover:text-white"
                      )}
                    >
                      {policy.label}
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
              Vesquiri detected likely ways these files or sheets relate. Review them before starting analysis.
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
                placeholder="Optional: e.g. This is monthly sales data by store and product category. Higher values mean more revenue."
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
                placeholder="Optional: e.g. Join files by Store Name, compare this year vs last year, and focus on revenue changes."
                className="w-full resize-none rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-900 outline-none transition-colors placeholder:text-zinc-400 focus:border-blue-500 dark:border-zinc-800 dark:bg-zinc-950 dark:text-white"
              />
            </label>
          </div>
        </div>
      )}
    </div>
  )
}
