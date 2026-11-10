// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, expect, it } from "vitest"
import { ExecutiveSummary } from "./executive-summary"

afterEach(cleanup)

it("shows a plain explanation before the saved formula", () => {
  const summary = "Total revenue is 60."
  render(<ExecutiveSummary summary={summary} analysisEvidence={{ summary_checks: {
    method: "measured_facts_v1", facts: [{ id: "metric_0", text: summary,
      calculation: "SUM(revenue)", scope: "analysed file",
      explanation: "We added the filled-in numbers for revenue.",
      scope_explanation: "We used the entries included in this report." }],
  } }} />)
  expect(screen.getByText("What your data shows")).toBeTruthy()
  expect(screen.getByText("How we worked this out")).toBeTruthy()
  expect(screen.getByText("We added the filled-in numbers for revenue.")).toBeTruthy()
  const formula = screen.getByText("SUM(revenue)")
  expect(formula.closest("details")?.getAttribute("open")).toBeNull()
})

it("does not attach an explanation to a different summary", () => {
  render(<ExecutiveSummary summary="A separate user-written note." analysisEvidence={{ summary_checks: {
    method: "measured_facts_v1", facts: [{ id: "metric_0", text: "Revenue is 60.",
      calculation: "SUM(revenue)", scope: "analysed file", explanation: "Unrelated explanation" }],
  } }} />)
  expect(screen.queryByText("Unrelated explanation")).toBeNull()
})
