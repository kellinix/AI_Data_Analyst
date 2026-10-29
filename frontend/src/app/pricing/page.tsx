import type { Metadata } from "next"
import Link from "next/link"
import { ArrowRight, Check, Sparkles } from "lucide-react"
import { BrandLogo } from "@/components/layout/brand-logo"

export const metadata: Metadata = {
  title: "Pricing",
  description: "Try Zephyr free and see the planned Pro early-access price.",
}

const plans = [
  {
    name: "Free",
    price: "£0",
    description: "Explore your data and see whether Zephyr works for you.",
    analyses: "5 analyses each month",
    questions: "20 follow-up questions each month",
    storage: "100 MB of saved files",
    status: "Available now",
    accent: "from-cyan-400 to-blue-500",
    featured: false,
  },
  {
    name: "Pro",
    price: "£19",
    description: "More room for regular reporting and questions.",
    analyses: "20 analyses each month",
    questions: "100 follow-up questions each month",
    storage: "1 GB of saved files",
    status: "Planned early access",
    accent: "from-violet-500 to-fuchsia-500",
    featured: true,
  },
] as const

export default function PricingPage() {
  return (
    <div className="min-h-screen bg-[#100d1b] text-white">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[560px] bg-[radial-gradient(ellipse_at_50%_0%,rgba(139,92,246,0.25),transparent_64%)]" />
      <header className="relative mx-auto flex max-w-7xl items-center justify-between px-5 py-6 sm:px-8">
        <Link href="/" aria-label="Zephyr home"><BrandLogo wordmarkClassName="!text-white [&_span]:!text-[#a8f0dc]" /></Link>
        <nav className="flex items-center gap-3 text-sm font-medium">
          <Link href="/login" className="rounded-xl px-4 py-2 text-white/70 hover:text-white">Sign in</Link>
          <Link href="/register" className="rounded-xl bg-white px-4 py-2 text-[#211b3a] hover:bg-violet-100">Get started</Link>
        </nav>
      </header>

      <main className="relative mx-auto max-w-7xl px-5 pb-20 pt-12 sm:px-8 sm:pt-20">
        <div className="mx-auto max-w-3xl text-center">
          <p className="mb-4 inline-flex items-center gap-2 rounded-full border border-cyan-300/20 bg-cyan-300/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-cyan-200">
            <Sparkles className="h-4 w-4" /> Simple plans
          </p>
          <h1 className="text-4xl font-bold tracking-tight sm:text-6xl">Start free. Make sense of your data.</h1>
          <p className="mx-auto mt-6 max-w-2xl text-base leading-7 text-violet-100/70 sm:text-lg">
            Try Zephyr with your own spreadsheet during our free pilot. A Pro plan with more analyses and follow-up questions is planned for later.
          </p>
        </div>

        <div className="mx-auto mt-14 grid max-w-4xl gap-5 md:grid-cols-2">
          {plans.map((plan) => (
            <section key={plan.name} className={`relative overflow-hidden rounded-[28px] border bg-[#211b33] p-7 shadow-2xl shadow-black/15 sm:p-8 ${plan.featured ? "border-fuchsia-400/60" : "border-white/10"}`}>
              <div className={`absolute inset-x-0 top-0 h-1 bg-gradient-to-r ${plan.accent}`} />
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-2xl font-semibold">{plan.name}</h2>
                <span className={`rounded-full px-3 py-1 text-xs font-medium ${plan.featured ? "bg-fuchsia-400/15 text-fuchsia-200" : "bg-white/10 text-violet-100/75"}`}>{plan.status}</span>
              </div>
              <p className="mt-3 min-h-14 text-sm leading-6 text-violet-100/70">{plan.description}</p>
              <p className="mt-7 text-5xl font-bold tracking-tight">{plan.price}<span className="ml-1 text-base font-normal text-violet-100/60">/ month</span></p>
              <ul className="mt-8 space-y-4 border-t border-white/10 pt-7 text-sm">
                {[plan.analyses, plan.questions, plan.storage].map((benefit) => (
                  <li key={benefit} className="flex items-start gap-3"><Check className="mt-0.5 h-4 w-4 shrink-0 text-cyan-300" /><span>{benefit}</span></li>
                ))}
              </ul>
              {plan.name === "Free" ? (
                <Link href="/register" className="mt-9 flex h-12 items-center justify-center gap-2 rounded-xl bg-white font-semibold text-[#211b3a] transition hover:bg-violet-100">
                  Start free <ArrowRight className="h-4 w-4" />
                </Link>
              ) : (
                <p className="mt-9 flex h-12 items-center justify-center rounded-xl border border-white/15 bg-white/5 text-sm font-medium text-violet-100/70">Pro is not available to purchase yet</p>
              )}
            </section>
          ))}
        </div>

        <div className="mt-8 rounded-2xl border border-amber-300/25 bg-amber-300/10 p-5 text-sm leading-6 text-amber-100/90">
          £19/month is the planned introductory Pro price. Signing up now starts a free account and will not charge you. Pro will open after pilot testing; you will choose whether to subscribe when it becomes available.
        </div>
      </main>
    </div>
  )
}
