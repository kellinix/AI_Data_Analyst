import { UploadWorkspace } from "@/components/upload/upload-workspace"

export default function UploadPage() {
  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-8 px-6 py-10">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-white">
          New analysis
        </h1>
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          Upload a CSV, Excel, JSON, Parquet, or TSV file to generate a dashboard.
        </p>
      </div>

      <UploadWorkspace />
    </div>
  )
}
