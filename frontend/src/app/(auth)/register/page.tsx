import type { Metadata } from "next"
import { Suspense } from "react"
import { AuthSwitchLink } from "@/components/auth/auth-switch-link"
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
          Start with a free account
        </p>
      </div>
      <Suspense fallback={null}>
        <RegisterForm />
      </Suspense>
      <p className="text-center text-sm text-zinc-500">
        Already have an account?{" "}
        <Suspense fallback={null}>
          <AuthSwitchLink to="/login">Sign in</AuthSwitchLink>
        </Suspense>
      </p>
    </div>
  )
}
