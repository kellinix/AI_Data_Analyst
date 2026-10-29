"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { isAxiosError } from "axios"
import { Loader2 } from "lucide-react"
import { toast } from "sonner"
import { useAuth } from "@/hooks/use-auth"
import { get, post } from "@/lib/api/client"
import { useAuthStore } from "@/stores/auth.store"
import type { UserProfile } from "@/types"

type BillingLink = { url: string }

function billingError(error: unknown): string {
  const detail = isAxiosError(error) ? error.response?.data?.detail : undefined
  return typeof detail === "string" ? detail : "Billing is unavailable right now. Please try again."
}

export function BillingAction({ location }: { location: "pricing" | "settings" }) {
  const { user, profile, isLoading } = useAuth()
  const [enabled, setEnabled] = useState(false)
  const [checked, setChecked] = useState(false)
  const [busy, setBusy] = useState(false)
  const [awaitingConfirmation, setAwaitingConfirmation] = useState(false)
  const hasBillingAccount = Boolean(profile?.subscription?.stripe_customer_id)
  const hasSubscription = Boolean(
    profile?.subscription?.stripe_subscription_id &&
    profile.subscription.status !== "canceled" &&
    profile.subscription.status !== "cancelled"
  )

  useEffect(() => {
    let live = true
    get<{ enabled: boolean }>("/billing/availability")
      .then((result) => { if (live) setEnabled(result.enabled) })
      .catch(() => { if (live) setEnabled(false) })
      .finally(() => { if (live) setChecked(true) })
    return () => { live = false }
  }, [])

  useEffect(() => {
    if (location !== "settings" || !window.location.search.includes("billing=returned")) return
    let live = true
    let attempts = 0
    setAwaitingConfirmation(true)
    const timer = window.setInterval(async () => {
      if (!live) return
      attempts += 1
      try {
        const updated = await get<UserProfile>("/users/me")
        if (!live) return
        useAuthStore.getState().setProfile(updated)
        if (updated.plan === "starter") {
          setAwaitingConfirmation(false)
          toast.success("Your Pro plan is ready")
          window.clearInterval(timer)
        }
      } catch {
        // Keep the confirmation message while Stripe's webhook is pending.
      }
      if (attempts >= 10) {
        setAwaitingConfirmation(false)
        window.clearInterval(timer)
      }
    }, 3000)
    return () => { live = false; window.clearInterval(timer) }
  }, [location])

  const openBilling = async (kind: "checkout" | "portal") => {
    setBusy(true)
    try {
      const result = await post<BillingLink>(`/billing/${kind}`)
      window.location.assign(result.url)
    } catch (error) {
      toast.error(billingError(error))
      setBusy(false)
    }
  }

  if (!checked || isLoading) {
    return <p className="mt-5 text-sm text-zinc-500">Checking plan availability…</p>
  }

  if (awaitingConfirmation && !hasSubscription) {
    return <p role="status" className="mt-5 text-sm text-amber-700 dark:text-amber-300">Stripe is confirming your payment. Your plan will update here shortly.</p>
  }

  if (hasSubscription || (location === "settings" && hasBillingAccount)) {
    return (
      <button type="button" disabled={busy} onClick={() => openBilling("portal")}
        className="mt-5 inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-violet-600 px-5 font-semibold text-white disabled:opacity-60">
        {busy && <Loader2 className="h-4 w-4 animate-spin" />} Manage billing
      </button>
    )
  }

  if (!enabled) {
    return <p className="mt-5 rounded-xl border border-white/15 bg-white/5 px-4 py-3 text-sm text-violet-100/80 dark:border-zinc-700 dark:text-zinc-300">Pro subscriptions are not open yet. Your free account will not be charged.</p>
  }

  if (!user) {
    return <Link href="/register" className="mt-5 inline-flex min-h-12 items-center justify-center rounded-xl bg-violet-600 px-5 font-semibold text-white">Create an account to choose Pro</Link>
  }

  return (
    <button type="button" disabled={busy || !profile} onClick={() => openBilling("checkout")}
      className="mt-5 inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-violet-600 px-5 font-semibold text-white disabled:opacity-60">
      {busy && <Loader2 className="h-4 w-4 animate-spin" />} Continue to secure checkout
    </button>
  )
}
