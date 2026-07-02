export function AnalysesGridSkeleton() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {Array.from({ length: 8 }).map((_, i) => (
        <div
          key={i}
          className="flex flex-col gap-4 rounded-2xl border bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900/60"
        >
          <div className="flex items-start justify-between">
            <div className="h-10 w-10 animate-pulse rounded-xl bg-zinc-100 dark:bg-zinc-800" />
          </div>
          <div className="space-y-2">
            <div className="h-3.5 w-3/4 animate-pulse rounded-md bg-zinc-100 dark:bg-zinc-800" />
            <div className="h-3 w-1/2 animate-pulse rounded-md bg-zinc-100 dark:bg-zinc-800" />
          </div>
          <div className="flex items-center justify-between">
            <div className="h-5 w-16 animate-pulse rounded-full bg-zinc-100 dark:bg-zinc-800" />
            <div className="h-3 w-20 animate-pulse rounded-md bg-zinc-100 dark:bg-zinc-800" />
          </div>
        </div>
      ))}
    </div>
  )
}
