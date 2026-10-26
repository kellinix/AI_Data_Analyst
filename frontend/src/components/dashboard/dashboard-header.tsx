"use client"

import Link from "next/link"
import { ArrowUpRight, Sparkles } from "lucide-react"
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
    <div className="relative isolate overflow-hidden rounded-[2rem] bg-[#302056] px-7 py-8 text-white shadow-xl shadow-violet-950/15 sm:px-10 sm:py-10">
      <div className="pointer-events-none absolute -right-12 -top-20 h-72 w-72 rounded-full bg-fuchsia-400/25 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-32 right-32 h-64 w-64 rounded-full bg-teal-300/20 blur-3xl" />
      <div className="relative flex flex-wrap items-end justify-between gap-6">
      <div>
        <p className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-[.18em] text-teal-200"><Sparkles className="h-4 w-4" /> Your data workspace</p>
        <h1 className="text-3xl font-bold tracking-tight text-white sm:text-4xl">
          {greeting()}{firstName ? `, ${firstName}` : ""}.
        </h1>
        <p className="mt-3 max-w-lg text-sm leading-6 text-violet-100/80">
          See the story in your data. Explore your latest analyses or start with a fresh file.
        </p>
      </div>
      <Link href="/upload" className="inline-flex items-center gap-2 rounded-xl bg-[#b5f3d8] px-5 py-3 text-sm font-bold text-[#203c39] shadow-lg shadow-black/10 transition-transform hover:-translate-y-0.5">Create analysis <ArrowUpRight className="h-4 w-4" /></Link>
      </div>
    </div>
  )
}
