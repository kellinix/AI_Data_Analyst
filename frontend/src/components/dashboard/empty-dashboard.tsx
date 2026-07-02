"use client"

import Link from "next/link"
import { motion } from "framer-motion"
import { Upload, Sparkles } from "lucide-react"

export function EmptyDashboard() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="flex flex-col items-center justify-center gap-6 rounded-2xl border-2 border-dashed border-zinc-200 bg-white py-24 text-center dark:border-zinc-800 dark:bg-zinc-900/20"
    >
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-blue-50 dark:bg-blue-900/30">
        <Sparkles className="h-8 w-8 text-blue-600 dark:text-blue-400" />
      </div>
      <div className="space-y-2">
        <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
          No analyses yet
        </h2>
        <p className="max-w-sm text-sm text-zinc-500">
          Upload your first file and get an executive dashboard, KPIs, and AI
          insights in seconds.
        </p>
      </div>
      <Link
        href="/upload"
        className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-blue-500"
      >
        <Upload className="h-4 w-4" />
        Upload your first file
      </Link>
    </motion.div>
  )
}
