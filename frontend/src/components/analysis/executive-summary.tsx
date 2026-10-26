"use client"

import { motion } from "framer-motion"
import { Sparkles } from "lucide-react"

interface ExecutiveSummaryProps {
  summary: string
  analysisEvidence?: unknown
}

interface SummaryFact {
  id: string
  text: string
  calculation: string
  scope: string
}

function matchingFacts(summary: string, evidence: unknown): SummaryFact[] {
  if (!evidence || typeof evidence !== "object") return []
  const checks = (evidence as Record<string, unknown>).summary_checks
  if (!checks || typeof checks !== "object") return []
  const { method, facts } = checks as Record<string, unknown>
  if (method !== "measured_facts_v1" || !Array.isArray(facts)) return []
  const valid = facts.filter((fact): fact is SummaryFact => fact &&
    typeof fact.id === "string" && typeof fact.text === "string" &&
    typeof fact.calculation === "string" && typeof fact.scope === "string")
  return valid.map((fact) => fact.text).join("\n") === summary ? valid : []
}

export function ExecutiveSummary({ summary, analysisEvidence }: ExecutiveSummaryProps) {
  const facts = matchingFacts(summary, analysisEvidence)
  // Split summary into sentences for better formatting
  const sentences = facts.length ? facts.map((fact) => fact.text) : summary
    .split(/(?<=[.!?])\s+/)
    .filter((s) => s.trim().length > 0)

  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <div className="zephyr-summary relative overflow-hidden rounded-3xl border border-violet-200 p-7 shadow-sm dark:border-[#554572]">
        <div className="mb-4 flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-violet-600 shadow-md shadow-violet-600/25">
            <Sparkles className="h-4 w-4 text-white" />
          </div>
          <h2 className="text-base font-semibold text-zinc-900 dark:text-white">
            The story at a glance
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
              <span className="mt-1.5 flex h-2 w-2 flex-shrink-0 rounded-full bg-teal-500" />
              <div>
                {sentence}
                {facts[i] && (
                  <details className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">
                    <summary className="cursor-pointer text-violet-700 dark:text-violet-300">How calculated</summary>
                    <p className="mt-1">{facts[i].calculation}. Scope: {facts[i].scope}.</p>
                  </details>
                )}
              </div>
            </motion.li>
          ))}
        </ul>
      </div>
    </motion.section>
  )
}
