import type { Metadata } from "next"
import { Suspense } from "react"
import { RegisterForm } from "@/components/auth/register-form"

export const metadata: Metadata = {
  title: "Create account",
}

export default function RegisterPage() {
  return (
    <div className="w-full max-w-sm space-y-6">
      <div className="space-y-1.5">
        <h1 className="text-2xl font-bold tracking-tight text-zinc-900 dark:text-white">
          Create your account
        </h1>
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          Start analysing your data with AI — free for 14 days
        </p>
      </div>
      <Suspense fallback={null}>
        <RegisterForm />
      </Suspense>
      <p className="text-center text-sm text-zinc-500">
        Already have an account?{" "}
        <a
          href="/login"
          className="font-medium text-blue-600 hover:text-blue-500 dark:text-blue-400"
        >
          Sign in
        </a>
      </p>
    </div>
  )
}
