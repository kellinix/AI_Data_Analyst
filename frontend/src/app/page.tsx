"use client"

import { motion, AnimatePresence } from "framer-motion"
import { useRouter } from "next/navigation"
import { useState, useCallback } from "react"
import { toast } from "sonner"
import { UploadZone } from "@/components/upload/upload-zone"
import { ProcessingAnimation } from "@/components/upload/processing-animation"
import { BrandLogo } from "@/components/layout/brand-logo"
import { useCreateAnalysis } from "@/hooks/use-analyses"
import { uploadsApi } from "@/lib/api/uploads"
import type { UploadedFile } from "@/types"

type PageState = "idle" | "uploading" | "processing" | "done"

function getErrorMessage(error: unknown): string {
  if (
    typeof error === "object" &&
    error !== null &&
    "response" in error &&
    typeof error.response === "object" &&
    error.response !== null &&
    "data" in error.response
  ) {
    const data = error.response.data as { detail?: unknown }
    if (typeof data.detail === "string") return data.detail
  }

  if (error instanceof Error) return error.message
  return "Please try again or check the backend logs."
}

export default function LandingPage() {
  const router = useRouter()
  const [state, setState] = useState<PageState>("idle")
  const [processingStep, setProcessingStep] = useState(0)
  const createAnalysis = useCreateAnalysis()

  const handleFileAccepted = useCallback(
    async (file: File) => {
      setState("uploading")
      try {
        const uploaded: UploadedFile = await uploadsApi.uploadFile(file)
        setState("processing")

        // Simulate processing steps while actual analysis runs in background
        const steps = [0, 1, 2, 3, 4, 5, 6]
        for (const step of steps) {
          setProcessingStep(step)
          await new Promise((r) => setTimeout(r, 600))
        }

        const analysis = await createAnalysis.mutateAsync({
          file_id: uploaded.id,
          name: file.name.replace(/\.[^.]+$/, ""),
        })

        setState("done")
        await new Promise((r) => setTimeout(r, 400))
        router.push(`/analysis/${analysis.id}`)
      } catch (error) {
        console.error("Upload or analysis creation failed", error)
        toast.error("Upload failed", {
          description: getErrorMessage(error),
        })
        setState("idle")
      }
    },
    [createAnalysis, router]
  )

  const handleFilesAccepted = useCallback(
    async (files: File[]) => {
      if (files[0]) {
        await handleFileAccepted(files[0])
      }
    },
    [handleFileAccepted]
  )

  return (
    <div className="relative flex min-h-screen flex-col bg-white dark:bg-zinc-950 overflow-hidden">
      {/* Subtle grid background */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          backgroundImage:
            "radial-gradient(circle at 1px 1px, rgb(0 0 0 / 0.04) 1px, transparent 0)",
          backgroundSize: "32px 32px",
        }}
      />

      {/* Top nav */}
      <header className="relative z-10 flex items-center justify-between px-8 py-6">
        <BrandLogo />
        <nav className="flex items-center gap-1">
          <a
            href="/login"
            className="rounded-lg px-3.5 py-2 text-sm font-medium text-zinc-500 transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
          >
            Sign in
          </a>
          <a
            href="/register"
            className="rounded-lg bg-zinc-900 px-3.5 py-2 text-sm font-medium text-white transition-colors hover:bg-zinc-700 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-100"
          >
            Get started
          </a>
        </nav>
      </header>

      {/* Hero */}
      <main className="relative z-10 flex flex-1 flex-col items-center justify-center px-4 py-16">
        <AnimatePresence mode="wait">
          {state === "idle" || state === "uploading" ? (
            <motion.div
              key="hero"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
              className="flex w-full max-w-2xl flex-col items-center gap-8 text-center"
            >
              {/* Badge */}
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1, duration: 0.5 }}
                className="inline-flex items-center gap-1.5 rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700 dark:border-blue-900 dark:bg-blue-950 dark:text-blue-400"
              >
                <span className="relative flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-400 opacity-75" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-blue-500" />
                </span>
                Powered by GPT-4o · No configuration required
              </motion.div>

              {/* Headline */}
              <motion.h1
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.15, duration: 0.6 }}
                className="text-[52px] font-bold leading-[1.1] tracking-tight text-zinc-900 dark:text-white"
              >
                Your data,{" "}
                <span className="text-blue-600">understood</span>
                <br />
                in seconds.
              </motion.h1>

              {/* Subheadline */}
              <motion.p
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2, duration: 0.5 }}
                className="max-w-md text-[17px] leading-relaxed text-zinc-500 dark:text-zinc-400"
              >
                Upload any spreadsheet, CSV, or report. Get an executive
                dashboard, automatic KPIs, beautiful charts, and AI-powered
                recommendations — instantly.
              </motion.p>

              {/* Upload zone */}
              <motion.div
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.25, duration: 0.6 }}
                className="w-full"
              >
                <UploadZone
                  onFilesAccepted={handleFilesAccepted}
                  isUploading={state === "uploading"}
                />
              </motion.div>

              {/* Supported formats */}
              <motion.p
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.35 }}
                className="text-xs text-zinc-400 dark:text-zinc-600"
              >
                CSV · Excel · JSON · Parquet · TSV · Up to 500 MB
              </motion.p>
            </motion.div>
          ) : (
            <motion.div
              key="processing"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
              className="flex w-full max-w-md flex-col items-center gap-6"
            >
              <ProcessingAnimation step={processingStep} />
            </motion.div>
          )}
        </AnimatePresence>
      </main>

      {/* Social proof footer */}
      <AnimatePresence>
        {state === "idle" && (
          <motion.footer
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ delay: 0.5 }}
            className="relative z-10 pb-10 text-center"
          >
            <p className="text-xs text-zinc-400 dark:text-zinc-600">
              Trusted by 10,000+ analysts at companies like{" "}
              <span className="font-medium text-zinc-500">Acme Corp</span>,{" "}
              <span className="font-medium text-zinc-500">Globex</span>, and{" "}
              <span className="font-medium text-zinc-500">Initech</span>
            </p>
          </motion.footer>
        )}
      </AnimatePresence>
    </div>
  )
}
