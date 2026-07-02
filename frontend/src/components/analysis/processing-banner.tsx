"use client"

import { Loader2 } from "lucide-react"
import { Progress } from "@/components/ui/progress"

const STEPS = [
  "Reading file",
  "Detecting columns",
  "Understanding data",
  "Finding patterns",
  "Building KPIs",
  "Generating charts",
  "Writing insights",
  "Finalising dashboard",
]

interface ProcessingBannerProps {
  progress: number
}

function getCurrentStep(progress: number) {
  if (progress >= 90) return STEPS[7]
  if (progress >= 85) return STEPS[6]
  if (progress >= 75) return STEPS[5]
  if (progress >= 65) return STEPS[4]
  if (progress >= 50) return STEPS[3]
  if (progress >= 35) return STEPS[2]
  if (progress >= 15) return STEPS[1]
  return STEPS[0]
}

export function ProcessingBanner({ progress }: ProcessingBannerProps) {
  const boundedProgress = Math.max(0, Math.min(100, Math.round(progress)))
  const currentStep = getCurrentStep(boundedProgress)

  return (
    <div className="sticky top-0 z-20 border-b border-amber-200 bg-amber-50 px-8 py-3 dark:border-amber-900/50 dark:bg-amber-950/30">
      <div className="flex items-center gap-3">
        <Loader2 className="h-4 w-4 animate-spin text-amber-600 dark:text-amber-400" />
        <div className="flex flex-1 items-center gap-3">
          <span className="text-sm font-medium text-amber-800 dark:text-amber-300">
            {currentStep}
          </span>
          <Progress
            value={boundedProgress}
            className="h-1.5 flex-1 max-w-xs bg-amber-200 dark:bg-amber-900/50 [&>div]:bg-amber-500"
          />
          <span className="text-xs text-amber-600 dark:text-amber-400">
            {boundedProgress}%
          </span>
        </div>
      </div>
    </div>
  )
}
