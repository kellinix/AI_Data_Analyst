"use client"

import { useSearchParams } from "next/navigation"
import { safeRedirect } from "@/lib/safe-redirect"

/**
 * Link between the sign in and sign up pages that keeps the redirectTo
 * target, so switching forms does not lose where the visitor was heading.
 */
export function AuthSwitchLink({
  to,
  children,
}: {
  to: "/login" | "/register"
  children: React.ReactNode
}) {
  const searchParams = useSearchParams()
  const raw = searchParams.get("redirectTo")
  const href = raw
    ? `${to}?redirectTo=${encodeURIComponent(safeRedirect(raw))}`
    : to
  return (
    <a
      href={href}
      className="font-medium text-blue-600 hover:text-blue-500 dark:text-blue-400"
    >
      {children}
    </a>
  )
}
