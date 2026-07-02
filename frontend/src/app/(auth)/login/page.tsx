import type { Metadata } from "next"
import { Suspense } from "react"
import { LoginForm } from "@/components/auth/login-form"

export const metadata: Metadata = {
  title: "Sign in",
}

export default function LoginPage() {
  return (
    <div className="w-full max-w-sm space-y-6">
      <div className="space-y-1.5">
        <h1 className="text-2xl font-bold tracking-tight text-zinc-900 dark:text-white">
          Welcome back
        </h1>
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          Sign in to your account to continue
        </p>
      </div>
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
      <p className="text-center text-sm text-zinc-500">
        Don&apos;t have an account?{" "}
        <a
          href="/register"
          className="font-medium text-blue-600 hover:text-blue-500 dark:text-blue-400"
        >
          Sign up free
        </a>
      </p>
    </div>
  )
}
