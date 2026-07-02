import { useState, useCallback } from "react"
import { useDropzone, type Accept } from "react-dropzone"
import { useUploadStore } from "@/stores/upload.store"
import { uploadsApi } from "@/lib/api/uploads"
import type { UploadedFile } from "@/types"

const ACCEPTED_TYPES: Accept = {
  "text/csv": [".csv"],
  "application/vnd.ms-excel": [".xls"],
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [
    ".xlsx",
  ],
  "application/json": [".json"],
  "application/parquet": [".parquet"],
  "text/tab-separated-values": [".tsv"],
}

const MAX_FILE_SIZE = 512 * 1024 * 1024 // 512 MB

interface UseFileUploadOptions {
  onSuccess?: (file: UploadedFile) => void
  onError?: (error: string) => void
  maxFiles?: number
}

export function useFileUpload(options: UseFileUploadOptions = {}) {
  const { onSuccess, onError, maxFiles = 1 } = options
  const { files, addFiles, removeFile, setProgress, setUploading, reset } =
    useUploadStore()
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([])
  const [errors, setErrors] = useState<Record<string, string>>({})

  const uploadFile = useCallback(
    async (file: File) => {
      setErrors((prev) => {
        const next = { ...prev }
        delete next[file.name]
        return next
      })

      try {
        setUploading(true)
        const uploaded = await uploadsApi.uploadFile(file, (percent) => {
          setProgress(file.name, percent)
        })
        setUploadedFiles((prev) => [...prev, uploaded])
        onSuccess?.(uploaded)
        return uploaded
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : "Upload failed"
        setErrors((prev) => ({ ...prev, [file.name]: message }))
        onError?.(message)
        throw err
      } finally {
        setUploading(false)
      }
    },
    [onSuccess, onError, setProgress, setUploading]
  )

  const { getRootProps, getInputProps, isDragActive, isDragReject } =
    useDropzone({
      accept: ACCEPTED_TYPES,
      maxSize: MAX_FILE_SIZE,
      maxFiles,
      onDrop: (acceptedFiles, rejectedFiles) => {
        if (rejectedFiles.length > 0) {
          rejectedFiles.forEach(({ file, errors: fileErrors }) => {
            const message = fileErrors
              .map((e) => e.message)
              .join(", ")
            setErrors((prev) => ({ ...prev, [file.name]: message }))
          })
        }
        if (acceptedFiles.length > 0) {
          addFiles(acceptedFiles)
        }
      },
    })

  return {
    files,
    uploadedFiles,
    errors,
    isDragActive,
    isDragReject,
    getRootProps,
    getInputProps,
    uploadFile,
    removeFile,
    reset,
  }
}
