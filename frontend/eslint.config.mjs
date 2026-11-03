import nextVitals from "eslint-config-next/core-web-vitals"
import nextTypescript from "eslint-config-next/typescript"

export default [
  ...nextVitals,
  ...nextTypescript,
  // Next 16 adds these React compiler checks. Keep existing findings visible
  // while the affected dashboard effects are refactored separately.
  { rules: { "react-hooks/set-state-in-effect": "warn", "react-hooks/static-components": "warn" } },
]
