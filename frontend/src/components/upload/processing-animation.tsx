"use client"

import { motion } from "framer-motion"
import { CheckCircle2, Circle, Loader2 } from "lucide-react"

const PROCESSING_STEPS = [
  { label: "Reading file", sublabel: "Parsing structure and encoding" },
  { label: "Detecting columns", sublabel: "Identifying data types and formats" },
  { label: "Understanding data", sublabel: "Profiling distributions and relationships" },
  { label: "Finding patterns", sublabel: "Running statistical analysis" },
  { label: "Building KPIs", sublabel: "Detecting business metrics" },
  { label: "Generating charts", sublabel: "Selecting optimal visualisations" },
  { label: "Writing insights", sublabel: "GPT-4o is analysing your data" },
]

interface ProcessingAnimationProps {
  step: number
}

export function ProcessingAnimation({ step }: ProcessingAnimationProps) {
  return (
    <div className="w-full space-y-6 text-center">
      {/* Header */}
      <div className="space-y-2">
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ repeat: Infinity, duration: 2, ease: "linear" }}
          className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-600"
        >
          <svg
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            className="text-white"
          >
            <path
              d="M3 17L7.5 11L11 14L15.5 7L21 17"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </motion.div>
        <h2 className="text-xl font-bold text-zinc-900 dark:text-white">
          Analysing your data
        </h2>
        <p className="text-sm text-zinc-500">
          This takes around 15–30 seconds
        </p>
      </div>

      {/* Steps */}
      <div className="space-y-2.5 rounded-2xl border bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/50">
        {PROCESSING_STEPS.map((s, i) => {
          const isCompleted = i < step
          const isActive = i === step
          const isPending = i > step

          return (
            <motion.div
              key={s.label}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: isPending ? 0.4 : 1, x: 0 }}
              transition={{ delay: i * 0.05, duration: 0.3 }}
              className="flex items-center gap-3 text-left"
            >
              {isCompleted ? (
                <CheckCircle2 className="h-5 w-5 flex-shrink-0 text-emerald-500" />
              ) : isActive ? (
                <Loader2 className="h-5 w-5 flex-shrink-0 animate-spin text-blue-500" />
              ) : (
                <Circle className="h-5 w-5 flex-shrink-0 text-zinc-300 dark:text-zinc-700" />
              )}
              <div className="min-w-0 flex-1">
                <p
                  className={`text-sm font-medium ${
                    isCompleted
                      ? "text-zinc-500 line-through"
                      : isActive
                      ? "text-zinc-900 dark:text-white"
                      : "text-zinc-400 dark:text-zinc-600"
                  }`}
                >
                  {s.label}
                </p>
                {isActive && (
                  <motion.p
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    className="text-xs text-zinc-400"
                  >
                    {s.sublabel}
                  </motion.p>
                )}
              </div>
            </motion.div>
          )
        })}
      </div>

      {/* Progress bar */}
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
        <motion.div
          className="h-full rounded-full bg-blue-600"
          initial={{ width: "0%" }}
          animate={{
            width: `${Math.round((step / (PROCESSING_STEPS.length - 1)) * 100)}%`,
          }}
          transition={{ duration: 0.5, ease: "easeOut" }}
        />
      </div>
    </div>
  )
}
