"use client"

import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { toast } from "sonner"
import { Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { useAuth } from "@/hooks/use-auth"
import { patch } from "@/lib/api/client"

const profileSchema = z.object({
  full_name: z.string().min(2, "Name must be at least 2 characters"),
})

type ProfileFormValues = z.infer<typeof profileSchema>

export function SettingsForm() {
  const { user } = useAuth()

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
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : "Save changes"}
          </Button>
        </form>
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
          onClick={() => {
            if (confirm("Are you sure you want to delete your account? This cannot be undone.")) {
              toast.error("Account deletion is not yet implemented in this demo")
            }
          }}
        >
          Delete account
        </Button>
      </section>
    </div>
  )
}
