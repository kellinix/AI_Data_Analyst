"use client"

import { useCallback } from "react"
import { useDropzone } from "react-dropzone"
import { motion, AnimatePresence } from "framer-motion"
import { Upload, FileSpreadsheet, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"
import { formatBytes } from "@/lib/utils"

const ACCEPTED_TYPES = {
  "text/csv": [".csv"],
  "application/vnd.ms-excel": [".xls"],
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
  "application/json": [".json"],
  "application/octet-stream": [".parquet"],
  "text/tab-separated-values": [".tsv"],
}

const MAX_SIZE = 512 * 1024 * 1024 // 512 MB

interface UploadZoneProps {
  onFilesAccepted: (files: File[]) => void
  isUploading?: boolean
  className?: string
}

export function UploadZone({
  onFilesAccepted,
  isUploading = false,
  className,
}: UploadZoneProps) {
  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      if (acceptedFiles.length > 0 && !isUploading) {
        onFilesAccepted(acceptedFiles)
      }
    },
    [onFilesAccepted, isUploading]
  )

  const { getRootProps, getInputProps, isDragActive, isDragReject, fileRejections } =
    useDropzone({
      onDrop,
      accept: ACCEPTED_TYPES,
      maxSize: MAX_SIZE,
      disabled: isUploading,
      multiple: true,
    })

  const rejectionError = fileRejections[0]?.errors[0]?.message

  return (
    <div className={cn("w-full", className)}>
      <div
        {...getRootProps()}
        className={cn(
          "group relative flex cursor-pointer flex-col items-center justify-center gap-4 rounded-2xl border-2 border-dashed p-12 transition-all duration-200",
          isDragActive && !isDragReject
            ? "border-blue-500 bg-blue-50 dark:bg-blue-950/30"
            : isDragReject
            ? "border-red-400 bg-red-50 dark:bg-red-950/30"
            : isUploading
            ? "border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900/50"
            : "border-zinc-200 bg-zinc-50/50 hover:border-zinc-300 hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900/20 dark:hover:border-zinc-700"
        )}
      >
        <input {...getInputProps()} />

        <AnimatePresence mode="wait">
          {isUploading ? (
            <motion.div
              key="uploading"
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              className="flex flex-col items-center gap-3"
            >
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-100 dark:bg-blue-900/40">
                <Loader2 className="h-6 w-6 animate-spin text-blue-600" />
              </div>
              <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                Uploading your file...
              </p>
            </motion.div>
          ) : isDragActive && !isDragReject ? (
            <motion.div
              key="drag-active"
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              className="flex flex-col items-center gap-3"
            >
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-100 dark:bg-blue-900/40">
                <Upload className="h-6 w-6 text-blue-600" />
              </div>
              <p className="text-sm font-medium text-blue-600">Drop to analyse</p>
            </motion.div>
          ) : (
            <motion.div
              key="idle"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex flex-col items-center gap-4"
            >
              {/* Icon cluster */}
              <div className="relative flex items-center justify-center">
                <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-white shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-800 dark:ring-white/10">
                  <FileSpreadsheet className="h-7 w-7 text-zinc-400 transition-colors group-hover:text-blue-500" />
                </div>
                <motion.div
                  animate={{ y: [0, -3, 0] }}
                  transition={{ repeat: Infinity, duration: 2.5, ease: "easeInOut" }}
                  className="absolute -right-5 -top-2 flex h-8 w-8 items-center justify-center rounded-xl bg-blue-600 shadow-md"
                >
                  <Upload className="h-4 w-4 text-white" />
                </motion.div>
              </div>

              <div className="space-y-1 text-center">
                <p className="text-[15px] font-semibold text-zinc-900 dark:text-white">
                  Drop files here
                </p>
                <p className="text-sm text-zinc-500 dark:text-zinc-400">
                  or{" "}
                  <span className="font-medium text-blue-600 group-hover:underline">
                    browse to add files
                  </span>
                </p>
              </div>

              {/* Format chips */}
              <div className="flex flex-wrap items-center justify-center gap-1.5">
                {["CSV", "Excel", "JSON", "Parquet", "TSV"].map((fmt) => (
                  <span
                    key={fmt}
                    className="rounded-md bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400"
                  >
                    {fmt}
                  </span>
                ))}
                <span className="text-xs text-zinc-400">
                  / up to {formatBytes(MAX_SIZE)}
                </span>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Error message */}
      <AnimatePresence>
        {(rejectionError || isDragReject) && (
          <motion.p
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className="mt-2 text-center text-xs text-red-500"
          >
            {rejectionError ?? "File type not supported"}
          </motion.p>
        )}
      </AnimatePresence>
    </div>
  )
}
