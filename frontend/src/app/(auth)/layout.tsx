import type { Metadata } from "next"
import Link from "next/link"
import { BrandLogo } from "@/components/layout/brand-logo"

export const metadata: Metadata = {
  title: "Sign in",
}

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      {/* Left: Form */}
      <div className="flex flex-col items-center justify-center px-8 py-12">
        {/* Logo */}
        <div className="mb-12 w-full max-w-sm">
          <Link href="/" className="inline-flex items-center gap-2">
            <BrandLogo />
          </Link>
        </div>
        {children}
      </div>

      {/* Right: Marketing panel */}
      <div className="hidden bg-zinc-950 lg:flex lg:flex-col lg:items-center lg:justify-center lg:px-16">
        <div className="max-w-sm space-y-8">
          {/* Headline */}
          <div className="space-y-3">
            <p className="text-sm font-medium uppercase tracking-widest text-blue-400">
              What you&apos;ll get
            </p>
            <h2 className="text-3xl font-bold leading-tight text-white">
              From spreadsheet to strategic insight in seconds
            </h2>
          </div>

          {/* Features list */}
          <ul className="space-y-4">
            {[
              {
                icon: "⚡",
                title: "Instant KPI detection",
                desc: "Revenue, profit, churn, and more — automatically.",
              },
              {
                icon: "🤖",
                title: "AI-powered insights",
                desc: "GPT-4o analyses your data and explains what matters.",
              },
              {
                icon: "💬",
                title: "Ask anything",
                desc: "Chat with your data like a senior analyst.",
              },
              {
                icon: "📊",
                title: "Beautiful charts",
                desc: "Automatically chosen, perfectly designed.",
              },
              {
                icon: "📋",
                title: "Actionable recommendations",
                desc: "Every suggestion tied to evidence and ROI.",
              },
            ].map((feature) => (
              <li key={feature.title} className="flex items-start gap-3">
                <span className="text-xl">{feature.icon}</span>
                <div>
                  <p className="text-sm font-medium text-white">
                    {feature.title}
                  </p>
                  <p className="text-sm text-zinc-400">{feature.desc}</p>
                </div>
              </li>
            ))}
          </ul>

          {/* Testimonial */}
          <div className="rounded-xl border border-white/10 bg-white/5 p-5">
            <p className="text-sm italic text-zinc-300">
              &ldquo;I uploaded our quarterly sales file and had a full
              executive briefing ready in under 30 seconds. Remarkable.&rdquo;
            </p>
            <div className="mt-3 flex items-center gap-2">
              <div className="h-7 w-7 rounded-full bg-gradient-to-br from-blue-400 to-violet-500" />
              <div>
                <p className="text-xs font-medium text-white">
                  Sarah Mitchell
                </p>
                <p className="text-xs text-zinc-500">VP Sales, Acme Corp</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
