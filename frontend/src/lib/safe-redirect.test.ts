import { describe, expect, it } from "vitest"
import { safeRedirect } from "./safe-redirect"

describe("safeRedirect", () => {
  it("keeps local paths and query strings", () => {
    expect(safeRedirect("/reset-password")).toBe("/reset-password")
    expect(safeRedirect("/analysis/123?view=chart")).toBe("/analysis/123?view=chart")
  })

  it.each([null, "", "https://evil.example", "//evil.example", ".evil.example", "javascript:alert(1)", "/\\evil.example", "/%5cevil.example", "/\n/evil.example"])("rejects unsafe redirect %s", (value) => {
    expect(safeRedirect(value)).toBe("/dashboard")
  })
})
