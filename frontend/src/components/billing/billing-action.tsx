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
type Offer = "monthly" | "weekly"
type Availability = { enabled: boolean; weekly_enabled?: boolean }

function billingError(error: unknown): string {
  const detail = isAxiosError(error) ? error.response?.data?.detail : undefined
  return typeof detail === "string" ? detail : "Billing is unavailable right now. Please try again."
}

export function BillingAction({ location, offer = "monthly" }: {
  location: "pricing" | "settings"; offer?: Offer
}) {
  const { user, profile, isLoading } = useAuth()
  const [availability, setAvailability] = useState<Availability>({ enabled: false })
  const [checked, setChecked] = useState(false)
  const [busy, setBusy] = useState(false)
  const [awaitingConfirmation, setAwaitingConfirmation] = useState(false)
  const hasBillingAccount = Boolean(profile?.subscription?.stripe_customer_id)
  const hasPass = profile?.plan === "starter" && Boolean(profile.pro_pass_expires_at)
  const hasSubscription = Boolean(
    profile?.subscription?.stripe_subscription_id &&
    profile.subscription.status !== "canceled" &&
    profile.subscription.status !== "cancelled"
  )

  useEffect(() => {
    let live = true
    get<Availability>("/billing/availability")
      .then((result) => { if (live) setAvailability(result) })
      .catch(() => { if (live) setAvailability({ enabled: false }) })
      .finally(() => { if (live) setChecked(true) })
    return () => { live = false }
  }, [])

  useEffect(() => {
    if (!profile?.pro_pass_expires_at) return
    const deadline = Date.parse(profile.pro_pass_expires_at)
    if (!Number.isFinite(deadline)) return
    let live = true
    const timer = window.setTimeout(() => {
      get<UserProfile>("/users/me")
        .then((updated) => { if (live) useAuthStore.getState().setProfile(updated) })
        .catch(() => { /* The API still enforces expiry on every protected request. */ })
    }, Math.max(0, deadline - Date.now()) + 250)
    return () => { live = false; window.clearTimeout(timer) }
  }, [profile?.pro_pass_expires_at])

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

  const openBilling = async (kind: "checkout" | "portal", selectedOffer: Offer = offer) => {
    setBusy(true)
    try {
      const result = await post<BillingLink>(`/billing/${kind}`, kind === "checkout" ? { offer: selectedOffer } : undefined)
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

  const manageBilling = (
    <button type="button" disabled={busy} onClick={() => openBilling("portal")}
      className="mt-5 inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-violet-600 px-5 font-semibold text-white disabled:opacity-60">
      {busy && <Loader2 className="h-4 w-4 animate-spin" />} Manage billing
    </button>
  )

  if (hasSubscription) return manageBilling

  if (hasPass) {
    return (
      <div className="mt-5 text-sm">
        <p>Your seven-day Pro pass ends on {new Date(profile!.pro_pass_expires_at!).toLocaleString()}. It does not renew.</p>
        {location === "settings" && hasBillingAccount && manageBilling}
      </div>
    )
  }

  const enabled = offer === "weekly" ? availability.weekly_enabled : availability.enabled
  const offers: Offer[] = location === "settings"
    ? (["monthly", "weekly"] as Offer[]).filter((item) => item === "weekly" ? availability.weekly_enabled : availability.enabled)
    : enabled ? [offer] : []

  if (offers.length === 0) {
    return <p className="mt-5 text-sm text-zinc-500">This Pro option is not available yet. Your free account will not be charged.</p>
  }

  if (!user) {
    return <Link href="/register" className="mt-5 inline-flex min-h-12 items-center justify-center rounded-xl bg-violet-600 px-5 font-semibold text-white">Create an account to choose Pro</Link>
  }

  return (
    <div className="mt-5 flex flex-wrap gap-3">
      {offers.map((item) => (
        <button key={item} type="button" disabled={busy || !profile} onClick={() => openBilling("checkout", item)}
          className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-violet-600 px-5 font-semibold text-white disabled:opacity-60">
          {busy && <Loader2 className="h-4 w-4 animate-spin" />}
          {item === "weekly" ? "Get 7 days · £5.99 once" : "Subscribe · £19/month"}
        </button>
      ))}
      {location === "settings" && hasBillingAccount && manageBilling}
    </div>
  )
}
