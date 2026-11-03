"use client"

import { useState, type FormEvent } from "react"
import Link from "next/link"
import { createClient } from "@/lib/supabase/client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("")
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState("")

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError("")
    try {
      const origin = process.env.NEXT_PUBLIC_APP_URL ?? window.location.origin
      const callback = new URL("/auth/callback", origin)
      callback.searchParams.set("redirectTo", "/reset-password")
      const result = await createClient().auth.resetPasswordForEmail(email.trim(), {
        redirectTo: callback.toString(),
      })
      if (result.error) throw result.error
      setSent(true)
    } catch {
      setError("We couldn't send the reset link. Please try again.")
    } finally {
      setBusy(false)
    }
  }

  return <div className="w-full max-w-sm space-y-6">
    <div><h1 className="text-2xl font-semibold">Reset your password</h1><p className="mt-2 text-sm text-zinc-600">Enter your account email and we’ll send you a reset link.</p></div>
    {sent ? <p role="status" className="text-sm">If an account exists for that email, check your inbox for a reset link. Open it in this browser.</p> :
      <form onSubmit={submit} className="space-y-4">
        <div className="space-y-2"><Label htmlFor="email">Email</Label><Input id="email" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} /></div>
        {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
        <Button type="submit" disabled={busy} className="w-full">{busy ? "Sending…" : "Send reset link"}</Button>
      </form>}
    <Link href="/login" className="text-sm underline">Back to sign in</Link>
  </div>
}
