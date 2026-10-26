"use client"

import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { analysesApi } from "@/lib/api/analyses"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import type { EvidenceEntryRequest } from "@/types"

export function EntryViewer({ analysisId, request, title = "View affected records" }: {
  analysisId: string; request: EvidenceEntryRequest; title?: string
}) {
  const [open, setOpen] = useState(false)
  const [offset, setOffset] = useState(0)
  const result = useQuery({ queryKey: ["evidence-entries", analysisId, request, offset],
    queryFn: () => analysesApi.entries(analysisId, { ...request, offset, limit: 25 }), enabled: open })
  return <><Button variant="outline" size="sm" className="mt-3" onClick={() => setOpen(true)}>{title}</Button>
    <Dialog open={open} onOpenChange={setOpen}><DialogContent className="max-w-5xl">
      <DialogHeader><DialogTitle>Records behind this finding</DialogTitle></DialogHeader>
      {result.isPending && <p>Finding the records…</p>}
      {result.error && <p role="alert">{(result.error as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? "Could not load the entries. Please try again."}</p>}
      {result.data && <>{result.data.record_context && <p className="text-sm">{result.data.record_context.description}</p>}<p className="text-sm text-zinc-600 dark:text-zinc-300">{result.data.matched_entries.toLocaleString()} matching {result.data.matched_entries === 1 ? (result.data.record_context?.singular ?? 'record') : (result.data.record_context?.plural ?? 'records')}. {result.data.scope}</p>
        {!result.data.matched_entries && <p>No matching entries were found.</p>}
        <div className="max-h-[60vh] overflow-auto"><table className="w-full text-left text-sm"><thead><tr><th className="p-2">Record</th>{result.data.columns.map((c) => <th key={c.name} className="whitespace-nowrap p-2">{c.label}</th>)}</tr></thead>
          <tbody>{result.data.entries.map((entry) => <tr key={entry.entry_number} className="border-t dark:border-zinc-700"><td className="min-w-[250px] p-2"><span>{entry.record_label ?? `Record ${entry.entry_number}`}</span><span className="mt-1 block text-xs text-zinc-500">Position {entry.entry_number} in the analysed file</span></td>{result.data!.columns.map((c) => <td key={c.name} className="whitespace-nowrap p-2">{entry.values[c.name] == null ? "Not provided" : typeof entry.values[c.name] === "number" ? (entry.values[c.name] as number).toLocaleString(undefined, { maximumFractionDigits: 20 }) : String(entry.values[c.name])}</td>)}</tr>)}</tbody></table></div>
        <div className="flex items-center justify-between"><Button variant="outline" disabled={!offset || result.isFetching} onClick={() => setOffset(Math.max(0, offset - 25))}>Previous</Button><span className="text-sm">{result.data.matched_entries ? offset + 1 : 0}–{offset + result.data.entries.length} of {result.data.matched_entries}</span><Button variant="outline" disabled={!result.data.has_more || result.isFetching} onClick={() => setOffset(offset + 25)}>Next</Button></div>
      </>}
    </DialogContent></Dialog></>
}
