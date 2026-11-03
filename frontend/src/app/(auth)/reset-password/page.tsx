"use client"

import { useState, type FormEvent } from "react"
import Link from "next/link"
import { createClient } from "@/lib/supabase/client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export default function ResetPasswordPage() {
  const [password, setPassword] = useState("")
  const [confirmation, setConfirmation] = useState("")
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState("")

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (password !== confirmation) { setError("Passwords do not match."); return }
    if (!/^(?=.*[A-Z])(?=.*\d).{8,}$/.test(password)) { setError("Use at least 8 characters, including an uppercase letter and a number."); return }
    setBusy(true)
    setError("")
    try {
      const { error: failure } = await createClient().auth.updateUser({ password })
      if (failure) throw failure
      setPassword("")
      setConfirmation("")
      setDone(true)
    } catch {
      setError("We couldn't update your password. Your link may have expired; request a new one.")
    } finally {
      setBusy(false)
    }
  }

  return <div className="w-full max-w-sm space-y-6">
    <div><h1 className="text-2xl font-semibold">Choose a new password</h1><p className="mt-2 text-sm text-zinc-600">Use at least 8 characters, including an uppercase letter and a number.</p></div>
    {done ? <p role="status" className="text-sm">Your password has been updated. <Link href="/dashboard" className="underline">Continue to your dashboard</Link>.</p> :
      <form onSubmit={submit} className="space-y-4">
        <div className="space-y-2"><Label htmlFor="password">New password</Label><Input id="password" type="password" autoComplete="new-password" minLength={8} required value={password} onChange={(event) => setPassword(event.target.value)} /></div>
        <div className="space-y-2"><Label htmlFor="confirmation">Confirm password</Label><Input id="confirmation" type="password" autoComplete="new-password" minLength={8} required value={confirmation} onChange={(event) => setConfirmation(event.target.value)} /></div>
        {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
        <Button type="submit" disabled={busy} className="w-full">{busy ? "Saving…" : "Save password"}</Button>
      </form>}
    {!done && <Link href="/forgot-password" className="text-sm underline">Request another link</Link>}
  </div>
}
