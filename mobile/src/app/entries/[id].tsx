import { useState } from 'react';
import { useLocalSearchParams } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { api, messageOf } from '../../lib/api';
import { entryValue, fieldLabel } from '../../lib/format';
import { useAuth } from '../../providers/auth';
import type { EvidenceEntries, EvidenceEntryRequest } from '../../generated/contracts';
import { Body, Button, Card, ErrorNotice, Label, Loading, Screen } from '../../components/ui';

export default function EntriesScreen() {
  const { id, request: encoded } = useLocalSearchParams<{ id: string; request: string }>();
  const { session } = useAuth();
  const [offset, setOffset] = useState(0);
  let request: EvidenceEntryRequest | null = null;
  try { request = JSON.parse(encoded) as EvidenceEntryRequest; } catch { /* Invalid links do not send a request. */ }
  const result = useQuery({ queryKey: ['entries', session?.user.id, id, encoded, offset], enabled: !!request,
    queryFn: ({ signal }) => api<EvidenceEntries>(`/analyses/${encodeURIComponent(id)}/entries`, { method: 'POST', body: { ...request, offset, limit: 10 }, signal }) });
  return <Screen><Label>Records behind this finding</Label>
    {!request && <ErrorNotice message="This entry link could not be opened. Return to the report and try again." />}
    {request && result.isPending && <Loading label="Finding the records…" />}
    {result.error && <ErrorNotice message={messageOf(result.error)} retry={() => void result.refetch()} />}
    {result.data && <>{result.data.record_context && <Body>{result.data.record_context.description}</Body>}<Body>{result.data.matched_entries.toLocaleString()} matching {result.data.matched_entries === 1 ? (result.data.record_context?.singular ?? 'record') : (result.data.record_context?.plural ?? 'records')}. {result.data.scope}</Body>
      {!result.data.entries.length && <Body>No matching entries were found.</Body>}
      {result.data.entries.map((entry) => <EntryCard key={entry.entry_number} entry={entry} columns={result.data!.columns} />)}
      <Body>Showing {result.data.matched_entries ? offset + 1 : 0}–{offset + result.data.entries.length} of {result.data.matched_entries}</Body>
      <Button title="Previous entries" variant="secondary" disabled={!offset || result.isFetching} onPress={() => setOffset(Math.max(0, offset - 10))} />
      <Button title="Next entries" variant="secondary" disabled={!result.data.has_more || result.isFetching} onPress={() => setOffset(offset + 10)} />
    </>}
  </Screen>;
}

function EntryCard({ entry, columns }: { entry: EvidenceEntries['entries'][number]; columns: EvidenceEntries['columns'] }) {
  const [expanded, setExpanded] = useState(false);
  return <Card><Label>{entry.record_label ?? `Record ${entry.entry_number}`}</Label><Body>Position {entry.entry_number} in the analysed file</Body>{(expanded ? columns : columns.slice(0, 5)).map((column) => <Body key={column.name}>{fieldLabel(column.label)}: {entryValue(entry.values[column.name], column.is_date)}</Body>)}
    {columns.length > 5 && <Button title={expanded ? 'Show less' : 'More record details'} variant="secondary" onPress={() => setExpanded((value) => !value)} />}
  </Card>;
}
