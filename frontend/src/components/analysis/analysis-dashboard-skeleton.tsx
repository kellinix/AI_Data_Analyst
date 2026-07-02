export function AnalysisDashboardSkeleton() {
  return (
    <div className="flex flex-col gap-8 p-8 animate-pulse">
      {/* Header */}
      <div className="space-y-2">
        <div className="h-8 w-64 rounded-lg bg-zinc-100 dark:bg-zinc-800" />
        <div className="h-4 w-48 rounded-md bg-zinc-100 dark:bg-zinc-800" />
      </div>

      {/* Executive summary */}
      <div className="rounded-2xl border border-zinc-100 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900/60">
        <div className="mb-4 h-5 w-40 rounded-md bg-zinc-100 dark:bg-zinc-800" />
        <div className="space-y-2">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-4 rounded-md bg-zinc-100 dark:bg-zinc-800" style={{ width: `${85 - i * 8}%` }} />
          ))}
        </div>
      </div>

      {/* KPIs */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="flex flex-col gap-4 rounded-2xl border bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900/60">
            <div className="flex items-center justify-between">
              <div className="h-4 w-24 rounded-md bg-zinc-100 dark:bg-zinc-800" />
              <div className="h-9 w-9 rounded-xl bg-zinc-100 dark:bg-zinc-800" />
            </div>
            <div className="space-y-2">
              <div className="h-8 w-32 rounded-lg bg-zinc-100 dark:bg-zinc-800" />
              <div className="h-4 w-20 rounded-md bg-zinc-100 dark:bg-zinc-800" />
            </div>
          </div>
        ))}
      </div>

      {/* Charts */}
      <div className="grid gap-5 md:grid-cols-2">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="rounded-2xl border bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900/60">
            <div className="mb-4 h-5 w-40 rounded-md bg-zinc-100 dark:bg-zinc-800" />
            <div className="h-64 rounded-xl bg-zinc-100 dark:bg-zinc-800" />
          </div>
        ))}
      </div>
    </div>
  )
}
