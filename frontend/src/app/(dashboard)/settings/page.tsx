import type { Metadata } from "next"
import { SettingsForm } from "@/components/settings/settings-form"

export const metadata: Metadata = {
  title: "Settings",
}

export default function SettingsPage() {
  return (
    <div className="mx-auto max-w-2xl p-8">
      <div className="mb-8 space-y-1">
        <h1 className="text-2xl font-bold tracking-tight text-zinc-900 dark:text-white">
          Settings
        </h1>
        <p className="text-sm text-zinc-500">
          Manage your account preferences and subscription
        </p>
      </div>
      <SettingsForm />
    </div>
  )
}
