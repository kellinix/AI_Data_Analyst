"use client"

import Link from "next/link"
import { motion } from "framer-motion"
import {
  BarChart3,
  Clock,
  MoreHorizontal,
  Trash2,
  RefreshCw,
  CheckCircle2,
  XCircle,
  Loader2,
} from "lucide-react"
import { formatRelativeTime } from "@/lib/utils"
import { useAnalyses, useDeleteAnalysis } from "@/hooks/use-analyses"
import { Badge } from "@/components/ui/badge"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { EmptyDashboard } from "@/components/dashboard/empty-dashboard"
import type { AnalysisListItem } from "@/types"
import { toast } from "sonner"

const statusConfig = {
  pending: {
    icon: Loader2,
    label: "Queued",
    variant: "secondary" as const,
    animate: false,
  },
  processing: {
    icon: Loader2,
    label: "Processing",
    variant: "warning" as const,
    animate: true,
  },
  completed: {
    icon: CheckCircle2,
    label: "Ready",
    variant: "success" as const,
    animate: false,
  },
  failed: {
    icon: XCircle,
    label: "Failed",
    variant: "destructive" as const,
    animate: false,
  },
}

function AnalysisCard({
  analysis,
  index,
}: {
  analysis: AnalysisListItem
  index: number
}) {
  const deleteAnalysis = useDeleteAnalysis()
  const { icon: StatusIcon, label, variant, animate } = statusConfig[analysis.status]

  const handleDelete = async (e: React.MouseEvent) => {
    e.preventDefault()
    if (!confirm(`Delete "${analysis.name}"?`)) return
    try {
      await deleteAnalysis.mutateAsync(analysis.id)
      toast.success("Analysis deleted")
    } catch {
      toast.error("Failed to delete analysis")
    }
  }

  const isClickable = analysis.status === "completed"

  const CardContent = (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04, duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      className={`group relative flex flex-col gap-4 rounded-2xl border bg-white p-5 shadow-sm transition-all dark:border-zinc-800 dark:bg-zinc-900/60 ${
        isClickable
          ? "cursor-pointer hover:border-zinc-300 hover:shadow-md dark:hover:border-zinc-700"
          : "cursor-default"
      }`}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-blue-50 dark:bg-blue-900/30">
          <BarChart3 className="h-5 w-5 text-blue-600 dark:text-blue-400" />
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger
            className="flex h-7 w-7 items-center justify-center rounded-lg text-zinc-400 opacity-0 transition-all hover:bg-zinc-100 hover:text-zinc-600 group-hover:opacity-100 dark:hover:bg-zinc-800"
            onClick={(e) => e.preventDefault()}
          >
            <MoreHorizontal className="h-4 w-4" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem
              onClick={handleDelete}
              className="text-red-500 focus:text-red-500"
            >
              <Trash2 className="mr-2 h-4 w-4" />
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* Title */}
      <div className="space-y-1">
        <h3 className="line-clamp-2 text-sm font-semibold text-zinc-900 dark:text-white">
          {analysis.name}
        </h3>
        <p className="text-xs text-zinc-500">
          {analysis.row_count?.toLocaleString() ?? "—"} rows ·{" "}
          {analysis.column_count ?? "—"} columns
        </p>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between">
        <Badge variant={variant} className="text-[11px]">
          <StatusIcon
            className={`mr-1 h-3 w-3 ${animate ? "animate-spin" : ""}`}
          />
          {label}
        </Badge>
        <div className="flex items-center gap-1 text-[11px] text-zinc-400">
          <Clock className="h-3 w-3" />
          {formatRelativeTime(analysis.created_at)}
        </div>
      </div>
    </motion.div>
  )

  return isClickable ? (
    <Link href={`/analysis/${analysis.id}`}>{CardContent}</Link>
  ) : (
    CardContent
  )
}

export function AnalysesGrid() {
  const { data, isLoading } = useAnalyses({ limit: 50 })

  if (!data?.items?.length && !isLoading) {
    return <EmptyDashboard />
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {data?.items.map((analysis, i) => (
        <AnalysisCard key={analysis.id} analysis={analysis} index={i} />
      ))}
    </div>
  )
}
