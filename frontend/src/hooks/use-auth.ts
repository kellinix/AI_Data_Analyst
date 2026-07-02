import { useEffect, useCallback } from "react"
import { useRouter } from "next/navigation"
import { createClient } from "@/lib/supabase/client"
import { useAuthStore } from "@/stores/auth.store"
import { get } from "@/lib/api/client"
import type { UserProfile } from "@/types"

export function useAuth() {
  const { user, profile, isLoading, setUser, setProfile, setLoading, reset } =
    useAuthStore()
  const router = useRouter()
  const supabase = createClient()

  useEffect(() => {
    // Initial session load
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session?.user) {
        setUser({
          id: session.user.id,
          email: session.user.email!,
          full_name: session.user.user_metadata?.full_name ?? null,
          avatar_url: session.user.user_metadata?.avatar_url ?? null,
          plan: "free",
          created_at: session.user.created_at,
          updated_at: session.user.updated_at ?? session.user.created_at,
        })
        // Fetch full profile from backend
        get<UserProfile>("/users/me")
          .then(setProfile)
          .catch(() => {})
          .finally(() => setLoading(false))
      } else {
        setLoading(false)
      }
    })

    // Listen for auth changes
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (event, session) => {
      if (event === "SIGNED_IN" && session?.user) {
        setUser({
          id: session.user.id,
          email: session.user.email!,
          full_name: session.user.user_metadata?.full_name ?? null,
          avatar_url: session.user.user_metadata?.avatar_url ?? null,
          plan: "free",
          created_at: session.user.created_at,
          updated_at: session.user.updated_at ?? session.user.created_at,
        })
        get<UserProfile>("/users/me")
          .then(setProfile)
          .catch(() => {})
      } else if (event === "SIGNED_OUT") {
        reset()
        router.push("/login")
      } else if (event === "TOKEN_REFRESHED" && session?.user) {
        setUser({
          id: session.user.id,
          email: session.user.email!,
          full_name: session.user.user_metadata?.full_name ?? null,
          avatar_url: session.user.user_metadata?.avatar_url ?? null,
          plan: "free",
          created_at: session.user.created_at,
          updated_at: session.user.updated_at ?? session.user.created_at,
        })
      }
    })

    return () => subscription.unsubscribe()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const signOut = useCallback(async () => {
    await supabase.auth.signOut()
  }, [supabase.auth])

  return { user, profile, isLoading, signOut }
}
