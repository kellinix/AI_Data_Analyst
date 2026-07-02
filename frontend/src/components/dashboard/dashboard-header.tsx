"use client"

import { useAuth } from "@/hooks/use-auth"

export function DashboardHeader() {
  const { user } = useAuth()

  const greeting = () => {
    const hour = new Date().getHours()
    if (hour < 12) return "Good morning"
    if (hour < 18) return "Good afternoon"
    return "Good evening"
  }

  const firstName = user?.full_name?.split(" ")[0] ?? null

  return (
    <div className="flex items-center justify-between">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-zinc-900 dark:text-white">
          {greeting()}{firstName ? `, ${firstName}` : ""}.
        </h1>
        <p className="mt-0.5 text-sm text-zinc-500">
          Your analyses are ready to explore.
        </p>
      </div>
    </div>
  )
}
