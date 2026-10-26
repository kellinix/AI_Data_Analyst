"use client"

import { useForm } from "react-hook-form"
import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { useQueryClient } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { toast } from "sonner"
import { Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { useAuth } from "@/hooks/use-auth"
import { del, get, patch } from "@/lib/api/client"
import { createClient } from "@/lib/supabase/client"
import { useAuthStore } from "@/stores/auth.store"
import type { UsageLedgerSummary } from "@/types"

const profileSchema = z.object({
  full_name: z.string().min(2, "Name must be at least 2 characters"),
})

type ProfileFormValues = z.infer<typeof profileSchema>

export function SettingsForm() {
  const { user, profile } = useAuth()
  const [ledger, setLedger] = useState<UsageLedgerSummary | null>(null)
  const [ledgerError, setLedgerError] = useState(false)
  const [isDeleting, setDeleting] = useState(false)
  const router = useRouter()
  const queryClient = useQueryClient()

  useEffect(() => {
    let active = true
    get<UsageLedgerSummary>("/users/me/usage-ledger")
      .then((result) => { if (active) setLedger(result) })
      .catch(() => { if (active) setLedgerError(true) })
    return () => { active = false }
  }, [])

  const deleteAccount = async () => {
    if (!confirm("Permanently delete your account and all uploaded files, analyses, and chats? This cannot be undone.")) return
    setDeleting(true)
    try {
      await del<void>("/users/me")
    } catch (error) {
      const detail = isAxiosError(error) ? error.response?.data?.detail : undefined
      toast.error(typeof detail === "string" ? detail : "Failed to delete account. Please retry.")
      setDeleting(false)
      return
    }
    // The account is already deleted. Clear browser state even if remote
    // sign-out fails because its session no longer exists.
    try {
      await createClient().auth.signOut({ scope: "local" })
    } catch {
      // Navigation and local cache cleanup still run after account removal.
    } finally {
      queryClient.clear()
      useAuthStore.getState().reset()
      toast.success("Account deleted")
      router.replace("/login")
    }
  }

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ProfileFormValues>({
    resolver: zodResolver(profileSchema),
    defaultValues: { full_name: user?.full_name ?? "" },
  })

  const onSubmit = async (values: ProfileFormValues) => {
    try {
      await patch("/users/me", values)
      toast.success("Profile updated")
    } catch {
      toast.error("Failed to update profile")
    }
  }

  return (
    <div className="space-y-8">
      {/* Profile */}
      <section className="rounded-2xl border bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/60">
        <div className="mb-6">
          <h2 className="text-base font-semibold text-zinc-900 dark:text-white">
            Profile
          </h2>
          <p className="mt-0.5 text-sm text-zinc-500">
            Update your personal information
          </p>
        </div>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-1.5">
            <Label>Email</Label>
            <Input value={user?.email ?? ""} disabled className="bg-zinc-50 dark:bg-zinc-800/50" />
            <p className="text-xs text-zinc-400">Email cannot be changed here</p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="full_name">Full name</Label>
            <Input
              id="full_name"
              placeholder="Your full name"
              {...register("full_name")}
            />
            {errors.full_name && (
              <p className="text-xs text-red-500">{errors.full_name.message}</p>
            )}
          </div>
          <Button type="submit" disabled={isSubmitting || isDeleting}>
            {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : "Save changes"}
          </Button>
        </form>
      </section>

      <Separator />

      <section className="rounded-2xl border bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/60">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-white">Usage history</h2>
        <p className="mt-1 text-sm text-zinc-500">
          Current allowances use your existing monthly counters. This history records completed,
          pending and failed operations separately; it is not a bill or payment record.
        </p>
        {profile && (
          <div className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
            <div className="rounded-lg bg-zinc-50 p-3 dark:bg-zinc-800/50">
              <p className="text-zinc-500">Analyses against current allowance</p>
              <strong>{profile.usage.analyses_this_month} / {profile.usage.analyses_limit}</strong>
            </div>
            <div className="rounded-lg bg-zinc-50 p-3 dark:bg-zinc-800/50">
              <p className="text-zinc-500">AI follow-ups against current allowance</p>
              <strong>{profile.usage.ai_queries_this_month} / {profile.usage.ai_queries_limit}</strong>
            </div>
          </div>
        )}
        {ledger && (
          <div className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
            <div><p className="text-zinc-500">Completed analyses recorded</p>
              <strong>{ledger.analysis_completed_lifetime}</strong> total · {ledger.analysis_completed_this_month} this calendar month
            </div>
            <div><p className="text-zinc-500">Completed AI follow-ups recorded</p>
              <strong>{ledger.ai_completed_lifetime}</strong> total · {ledger.ai_completed_this_month} this calendar month
            </div>
            <div><p className="text-zinc-500">Pending / failed analyses</p>
              <strong>{ledger.analysis_reserved} / {ledger.analysis_failed}</strong>
            </div>
            <div><p className="text-zinc-500">Failed / unverified older AI replies</p>
              <strong>{ledger.ai_failed} / {ledger.ai_legacy_unknown}</strong>
            </div>
            <div className="sm:col-span-2"><p className="text-zinc-500">Provider tokens recorded for AI follow-ups</p>
              <strong>{(ledger.prompt_tokens_recorded + ledger.completion_tokens_recorded).toLocaleString()}</strong>
              <span className="text-zinc-500"> ({ledger.prompt_tokens_recorded.toLocaleString()} input, {ledger.completion_tokens_recorded.toLocaleString()} output)</span>
            </div>
          </div>
        )}
        {ledgerError && <p className="mt-3 text-sm text-amber-700">Usage history is temporarily unavailable.</p>}
      </section>

      <Separator />

      {/* Danger zone */}
      <section className="rounded-2xl border border-red-200 bg-white p-6 dark:border-red-900/40 dark:bg-zinc-900/60">
        <div className="mb-4">
          <h2 className="text-base font-semibold text-red-600">Danger zone</h2>
          <p className="mt-0.5 text-sm text-zinc-500">
            These actions are permanent and cannot be undone
          </p>
        </div>
        <Button
          variant="destructive"
          size="sm"
          disabled={isDeleting || isSubmitting}
          onClick={deleteAccount}
        >
          {isDeleting ? <Loader2 className="h-4 w-4 animate-spin" /> : "Delete account"}
        </Button>
      </section>
    </div>
  )
}
