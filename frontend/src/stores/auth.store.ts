import { create } from "zustand"
import { createJSONStorage, persist, type StateStorage } from "zustand/middleware"
import type { User, UserProfile } from "@/types"

// Node 25+ defines a server-side `localStorage` whose methods are undefined, so
// zustand's default storage passes its availability check during server
// rendering and then throws on getItem. Only touch storage in the browser.
const serverSafeStorage: StateStorage = {
  getItem: () => null,
  setItem: () => {},
  removeItem: () => {},
}

interface AuthState {
  user: User | null
  profile: UserProfile | null
  isLoading: boolean
  setUser: (user: User | null) => void
  setProfile: (profile: UserProfile | null) => void
  setLoading: (loading: boolean) => void
  reset: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      profile: null,
      isLoading: true,
      setUser: (user) => set({ user }),
      setProfile: (profile) => set({ profile }),
      setLoading: (isLoading) => set({ isLoading }),
      reset: () => set({ user: null, profile: null, isLoading: false }),
    }),
    {
      name: "auth-store",
      storage: createJSONStorage(() =>
        typeof window === "undefined" ? serverSafeStorage : window.localStorage
      ),
      partialize: (state) => ({ user: state.user }),
    }
  )
)
