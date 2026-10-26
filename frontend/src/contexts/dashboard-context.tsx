"use client"

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react"
import { analysesApi } from "@/lib/api/analyses"
import type { ActiveFilter, DashboardAction, DashboardPalette, DashboardState } from "@/types"

interface DashboardContextValue {
  layout: DashboardState | null
  loading: boolean
  saving: boolean
  error: string | null
  edit: (action: DashboardAction, chartId?: string, metricFamilyId?: string, filters?: ActiveFilter[], palette?: DashboardPalette) => Promise<boolean>
}

const DashboardContext = createContext<DashboardContextValue | null>(null)

export function DashboardProvider({ analysisId, enabled = true, children }: { analysisId: string; enabled?: boolean; children: ReactNode }) {
  const [layout, setLayout] = useState<DashboardState | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!enabled) { setLayout(null); setLoading(false); return }
    let active = true
    setLoading(true)
    analysesApi.getDashboard(analysisId).then((value) => {
      if (active) setLayout(value)
    }).catch(() => {
      if (active) setError("Saved dashboard is unavailable.")
    }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [analysisId, enabled])

  const edit = useCallback(async (action: DashboardAction, chartId?: string,
    metricFamilyId?: string, filters?: ActiveFilter[], palette?: DashboardPalette) => {
    if (!layout || saving) return false
    setSaving(true)
    setError(null)
    try {
      setLayout(await analysesApi.editDashboard(analysisId, layout.version, action, chartId, metricFamilyId, filters, palette))
      return true
    } catch {
      setError("Could not save the dashboard. The latest version has been loaded; try again.")
      try { setLayout(await analysesApi.getDashboard(analysisId)) } catch { /* Keep last good layout. */ }
      return false
    } finally { setSaving(false) }
  }, [analysisId, layout, saving])

  const value = useMemo(() => ({ layout, loading, saving, error, edit }), [layout, loading, saving, error, edit])
  return <DashboardContext.Provider value={value}>{children}</DashboardContext.Provider>
}

export function useDashboardContext() { return useContext(DashboardContext) }
