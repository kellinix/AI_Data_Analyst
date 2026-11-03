import Link from "next/link"
import type { ReactNode } from "react"
import { BrandLogo } from "@/components/layout/brand-logo"

export function LegalPage({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="mx-auto flex max-w-4xl items-center justify-between gap-4 px-5 py-6">
        <Link href="/" aria-label="Vesquiri home"><BrandLogo /></Link>
        <Link href="/login" className="text-sm underline underline-offset-4">Sign in</Link>
      </header>
      <main className="mx-auto max-w-4xl px-5 py-10">
        <h1 className="text-3xl font-bold tracking-tight">{title}</h1>
        <p className="mt-3 text-sm text-muted-foreground">Last updated: 3 November 2026</p>
        <article className="prose prose-slate mt-8 max-w-none dark:prose-invert">{children}</article>
      </main>
      <footer className="mx-auto flex max-w-4xl flex-wrap gap-5 border-t px-5 py-6 text-sm">
        <Link href="/privacy" className="underline underline-offset-4">Privacy policy</Link>
        <Link href="/terms" className="underline underline-offset-4">Terms of use</Link>
        <Link href="/delete-account" className="underline underline-offset-4">Delete your account</Link>
      </footer>
    </div>
  )
}
