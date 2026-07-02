"use client"

import { motion } from "framer-motion"
import { MoreHorizontal, Download, RefreshCw, Share2 } from "lucide-react"
import { toast } from "sonner"
import { useQueryClient } from "@tanstack/react-query"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { analysesApi } from "@/lib/api/analyses"
import { analysisKeys } from "@/hooks/use-analyses"
import { formatDate } from "@/lib/utils"
import type { Analysis, AnalysisStatus } from "@/types"

interface AnalysisHeaderProps {
  analysis: Analysis
  status: AnalysisStatus
}

const statusMeta: Record<
  AnalysisStatus,
  { label: string; variant: "success" | "warning" | "destructive" | "secondary" }
> = {
  completed: { label: "Ready", variant: "success" },
  processing: { label: "In progress", variant: "warning" },
  pending: { label: "Queued", variant: "secondary" },
  failed: { label: "Failed", variant: "destructive" },
}

export function AnalysisHeader({ analysis, status }: AnalysisHeaderProps) {
  const queryClient = useQueryClient()
  const meta = statusMeta[status] ?? statusMeta.processing
  const uploadContext =
    analysis.metadata && typeof analysis.metadata === "object"
      ? (analysis.metadata.upload_context as Record<string, unknown> | undefined)
      : undefined
  const cleaning =
    uploadContext && typeof uploadContext.cleaning === "object"
      ? (uploadContext.cleaning as Record<string, unknown>)
      : undefined
  const hasCleanedDataset = Boolean(cleaning?.cleaned_csv_path)
  const hasProfileJson = Boolean(analysis.metadata?.profile_json_path)

  async function downloadBlob(
    load: () => Promise<Blob>,
    filename: string,
    errorMessage: string
  ) {
    try {
      const blob = await load()
      const url = URL.createObjectURL(blob)
      const link = document.createElement("a")
      link.href = url
      link.download = filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    } catch (error) {
      console.error(errorMessage, error)
      toast.error(errorMessage)
    }
  }

  function downloadCleanedDataset() {
    return downloadBlob(
      () => analysesApi.downloadCleaned(analysis.id),
      `${analysis.name.replace(/\s+/g, "_").toLowerCase()}_cleaned.csv`,
      "Cleaned dataset download failed"
    )
  }

  function downloadProfileJson() {
    return downloadBlob(
      () => analysesApi.downloadProfileJson(analysis.id),
      `${analysis.name.replace(/\s+/g, "_").toLowerCase()}_profile.json`,
      "Profile JSON download failed"
    )
  }

  async function rerunAnalysis() {
    try {
      await analysesApi.rerun(analysis.id)
      toast.success("Analysis restarted")
      queryClient.invalidateQueries({ queryKey: analysisKeys.detail(analysis.id) })
      queryClient.invalidateQueries({ queryKey: analysisKeys.status(analysis.id) })
    } catch (error) {
      console.error("Analysis restart failed", error)
      toast.error("Analysis restart failed")
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className="flex items-start justify-between gap-4"
    >
      <div className="space-y-1">
        <div className="flex items-center gap-2.5">
          <h1 className="text-2xl font-bold tracking-tight text-zinc-900 dark:text-white">
            {analysis.name}
          </h1>
          <Badge variant={meta.variant} className="text-xs">
            {meta.label}
          </Badge>
        </div>
        <p className="text-sm text-zinc-500">
          {analysis.row_count?.toLocaleString()} rows · {analysis.column_count} columns ·{" "}
          Analysed {formatDate(analysis.updated_at)}
        </p>
      </div>

      <div className="flex items-center gap-2">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="icon">
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {hasProfileJson && (
              <DropdownMenuItem onClick={downloadProfileJson}>
                <Download className="mr-2 h-4 w-4" />
                Download Profile JSON
              </DropdownMenuItem>
            )}
            {hasCleanedDataset && (
              <DropdownMenuItem onClick={downloadCleanedDataset}>
                <Download className="mr-2 h-4 w-4" />
                Download cleaned CSV
              </DropdownMenuItem>
            )}
            {(hasProfileJson || hasCleanedDataset) && <DropdownMenuSeparator />}
            <DropdownMenuItem>
              <Download className="mr-2 h-4 w-4" />
              Export PDF
            </DropdownMenuItem>
            <DropdownMenuItem>
              <Download className="mr-2 h-4 w-4" />
              Export Excel
            </DropdownMenuItem>
            <DropdownMenuItem>
              <Share2 className="mr-2 h-4 w-4" />
              Share link
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={rerunAnalysis}>
              <RefreshCw className="mr-2 h-4 w-4" />
              Re-analyse
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </motion.div>
  )
}
