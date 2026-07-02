"use client"

import { motion } from "framer-motion"
import { Sparkles } from "lucide-react"

interface ExecutiveSummaryProps {
  summary: string
}

export function ExecutiveSummary({ summary }: ExecutiveSummaryProps) {
  // Split summary into sentences for better formatting
  const sentences = summary
    .split(/(?<=[.!?])\s+/)
    .filter((s) => s.trim().length > 0)

  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <div className="rounded-2xl border border-blue-100 bg-gradient-to-br from-blue-50 to-indigo-50/50 p-6 dark:border-blue-900/40 dark:from-blue-950/30 dark:to-indigo-950/20">
        <div className="mb-4 flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600">
            <Sparkles className="h-4 w-4 text-white" />
          </div>
          <h2 className="text-base font-semibold text-zinc-900 dark:text-white">
            Executive Summary
          </h2>
        </div>
        <ul className="space-y-2">
          {sentences.map((sentence, i) => (
            <motion.li
              key={i}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.1 + i * 0.06, duration: 0.3 }}
              className="flex items-start gap-2.5 text-sm leading-relaxed text-zinc-700 dark:text-zinc-300"
            >
              <span className="mt-1.5 flex h-1.5 w-1.5 flex-shrink-0 rounded-full bg-blue-500" />
              {sentence}
            </motion.li>
          ))}
        </ul>
      </div>
    </motion.section>
  )
}
