import type { Metadata } from "next"
import { Suspense } from "react"
import { DashboardOverview } from "@/components/dashboard/dashboard-overview"
import { DashboardHeader } from "@/components/dashboard/dashboard-header"
import { AnalysesGridSkeleton } from "@/components/dashboard/analyses-grid-skeleton"

export const metadata: Metadata = {
  title: "Dashboard",
}

export default function DashboardPage() {
  return (
    <div className="flex flex-col gap-8 p-8">
      <DashboardHeader />
      <Suspense fallback={<AnalysesGridSkeleton />}>
        <DashboardOverview />
      </Suspense>
    </div>
  )
}
