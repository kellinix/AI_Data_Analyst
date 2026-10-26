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
    <div className="grid min-h-screen bg-[#f8f5fc] dark:bg-[#130f23] lg:grid-cols-2">
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
      <div className="relative hidden overflow-hidden bg-[#302056] lg:flex lg:flex-col lg:items-center lg:justify-center lg:px-16">
        <div className="absolute -right-24 -top-24 h-80 w-80 rounded-full bg-fuchsia-400/20 blur-3xl" />
        <div className="absolute -bottom-24 -left-16 h-80 w-80 rounded-full bg-teal-300/20 blur-3xl" />
        <div className="max-w-sm space-y-8">
          {/* Headline */}
          <div className="space-y-3">
            <p className="text-sm font-bold uppercase tracking-widest text-teal-200">
              What you&apos;ll get
            </p>
            <h2 className="text-3xl font-bold leading-tight text-white">
              Turn your data into a clearer picture.
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
                desc: "Plain-language summaries grounded in the analysed file.",
              },
              {
                icon: "💬",
                title: "Ask anything",
                desc: "Chat with your data like a senior analyst.",
              },
              {
                icon: "📊",
                title: "Beautiful charts",
                desc: "Explore useful views of the patterns in your data.",
              },
              {
                icon: "📋",
                title: "Actionable recommendations",
                desc: "Review recommendations alongside their supporting evidence.",
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

          <div className="flex items-end gap-3 rounded-3xl border border-white/15 bg-white/10 p-7 shadow-2xl shadow-black/10">
            {[36, 65, 48, 88, 71, 100, 79].map((height, index) => (
              <div key={index} className="flex-1 rounded-t-lg" style={{ height: `${height}px`, backgroundColor: ["#A98BFF", "#63D8C4", "#FFAD8C", "#E476C7"][index % 4] }} />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
