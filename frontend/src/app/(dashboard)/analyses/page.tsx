import type { Metadata } from "next"
import { Suspense } from "react"
import { AnalysesGrid } from "@/components/dashboard/analyses-grid"
import { AnalysesGridSkeleton } from "@/components/dashboard/analyses-grid-skeleton"

export const metadata: Metadata = {
  title: "Analyses",
}

export default function AnalysesPage() {
  return (
    <div className="flex flex-col gap-8 p-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-zinc-900 dark:text-white">
          Analyses
        </h1>
        <p className="mt-0.5 text-sm text-zinc-500">
          Review every uploaded file and generated dashboard.
        </p>
      </div>
      <Suspense fallback={<AnalysesGridSkeleton />}>
        <AnalysesGrid />
      </Suspense>
    </div>
  )
}
