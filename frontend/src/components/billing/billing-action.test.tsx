// @vitest-environment jsdom

import type { ReactNode } from "react"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { UserProfile } from "@/types"
import { BillingAction } from "./billing-action"

const mocks = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), setProfile: vi.fn(),
  auth: { user: { id: "test" }, profile: null as UserProfile | null, isLoading: false },
}))

vi.mock("@/hooks/use-auth", () => ({ useAuth: () => mocks.auth }))
vi.mock("@/lib/api/client", () => ({ get: mocks.get, post: mocks.post }))
vi.mock("@/stores/auth.store", () => ({
  useAuthStore: { getState: () => ({ setProfile: mocks.setProfile }) },
}))
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }))
vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a>,
}))

beforeEach(() => {
  vi.clearAllMocks()
  mocks.auth.profile = {
    id: "test", email: "test@example.test", full_name: null, avatar_url: null,
    plan: "free", created_at: "2026-01-01", updated_at: "2026-01-01",
    subscription: null, pro_pass_expires_at: null,
    usage: { analyses_this_month: 5, analyses_limit: 5, ai_queries_this_month: 1,
      ai_queries_limit: 20, storage_used_bytes: 0, storage_limit_bytes: 100000000 },
  }
  mocks.get.mockResolvedValue({ enabled: true, weekly_enabled: true })
  // Keep navigation pending; the assertion verifies the actual request sent by
  // the selected customer-facing button without navigating jsdom to Stripe.
  mocks.post.mockImplementation(() => new Promise(() => {}))
})

afterEach(cleanup)

describe("billing choices", () => {
  it("shows app-store access without offering a duplicate web purchase", async () => {
    mocks.auth.profile!.plan = "starter"
    mocks.auth.profile!.store_access_expires_at = new Date(Date.now() + 86400000).toISOString()
    render(<BillingAction location="settings" />)
    expect(await screen.findByText(/Manage subscriptions in the Apple or Google account/)).toBeTruthy()
    expect(screen.queryByRole("button", { name: /Subscribe|Get 7 days/ })).toBeNull()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it.each([
    ["weekly", "Get 7 days · £5.99 once"],
    ["monthly", "Subscribe · £19/month"],
  ] as const)("sends the %s offer chosen on Pricing", async (offer, name) => {
    render(<BillingAction location="pricing" offer={offer} />)
    fireEvent.click(await screen.findByRole("button", { name }))
    expect(mocks.post).toHaveBeenCalledWith("/billing/checkout", { offer })
  })

  it("offers both durations in Settings and sends the one-time choice", async () => {
    render(<BillingAction location="settings" />)
    const weekly = await screen.findByRole("button", { name: "Get 7 days · £5.99 once" })
    expect(screen.getByRole("button", { name: "Subscribe · £19/month" })).toBeTruthy()
    fireEvent.click(weekly)
    expect(mocks.post).toHaveBeenCalledWith("/billing/checkout", { offer: "weekly" })
  })

  it("shows an active pass deadline and prevents overlapping purchases", async () => {
    mocks.auth.profile!.plan = "starter"
    mocks.auth.profile!.pro_pass_expires_at = new Date(Date.now() + 86400000).toISOString()
    render(<BillingAction location="settings" />)
    expect(await screen.findByText(/It does not renew/)).toBeTruthy()
    expect(screen.queryByRole("button", { name: /Subscribe|Get 7 days/ })).toBeNull()
    expect(mocks.post).not.toHaveBeenCalled()
  })

  it("keeps weekly checkout closed when its price is unavailable", async () => {
    mocks.get.mockResolvedValue({ enabled: true, weekly_enabled: false })
    render(<BillingAction location="pricing" offer="weekly" />)
    expect(await screen.findByText(/not available yet/)).toBeTruthy()
    expect(screen.queryByRole("button")).toBeNull()
    expect(mocks.post).not.toHaveBeenCalled()
  })
})
