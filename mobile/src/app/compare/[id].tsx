import { useState } from 'react';
import { router, useLocalSearchParams } from 'expo-router';
import { useMutation, useQuery } from '@tanstack/react-query';
import { fieldLabel } from '../../lib/format';
import { api, messageOf } from '../../lib/api';
import { useAuth } from '../../providers/auth';
import type { Analysis, ComparisonPlan, ComparisonResult } from '../../generated/contracts';
import { Body, Button, Card, ErrorNotice, Label, Loading, Screen } from '../../components/ui';

export default function CompareScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { session } = useAuth();
  const [column, setColumn] = useState('');
  const [group, setGroup] = useState('');
  const [aggregation, setAggregation] = useState<'sum' | 'average' | 'count'>('average');
  const analysis = useQuery({ queryKey: ['analysis', session?.user.id, id], queryFn: ({ signal }) => api<Analysis>(`/analyses/${encodeURIComponent(id)}`, { signal }) });
  const schema = (analysis.data?.metadata?.schema ?? []) as { name: string; analysis_role?: string; is_numeric?: boolean; display_label?: string }[];
  const result = useMutation({ mutationFn: (plan: ComparisonPlan) => api<ComparisonResult>(`/analyses/${encodeURIComponent(id)}/compare`, { method: 'POST', body: plan }) });
  return <Screen><Label>Compare groups</Label><Body>Choose what to compare. Results use all entries in this report and are ordered from highest to lowest.</Body>
    {analysis.isPending && <Loading label="Opening your figures…" />}{analysis.error && <ErrorNotice message={messageOf(analysis.error)} />}
    <Card><Label>What do you want to compare?</Label>{(['sum', 'average', 'count'] as const).map((value) => <Button key={value} title={`${aggregation === value ? '✓ ' : ''}${{ sum: 'Total', average: 'Average per entry', count: 'Number of entries' }[value]}`} variant="secondary" onPress={() => setAggregation(value)} />)}</Card>
    {aggregation !== 'count' && <Card><Label>Choose a measure</Label>{schema.filter((c) => c.analysis_role === 'metric' && c.is_numeric).map((c) => <Button key={c.name} title={`${column === c.name ? '✓ ' : ''}${c.display_label ?? fieldLabel(c.name)}`} variant="secondary" onPress={() => setColumn(c.name)} />)}</Card>}
    <Card><Label>Compare by</Label>{schema.filter((c) => ['dimension', 'flag'].includes(c.analysis_role ?? '')).map((c) => <Button key={c.name} title={`${group === c.name ? '✓ ' : ''}${c.display_label ?? fieldLabel(c.name)}`} variant="secondary" onPress={() => setGroup(c.name)} />)}</Card>
    <Button title="Compare" disabled={!group || (aggregation !== 'count' && !column)} loading={result.isPending} onPress={() => result.mutate({ aggregation, column: aggregation === 'count' ? null : column, group_by: group })} />
    {result.error && <ErrorNotice message={messageOf(result.error)} />}
    {result.data && <><Label>{result.data.title}</Label><Body>{result.data.answer}</Body><Body>{result.data.scope}</Body>{result.data.groups.map((item, index) => <Card key={index}><Label>{item.group ?? 'Not provided'}</Label><Body>{item.value == null ? 'Not available' : item.value.toLocaleString(undefined, { maximumFractionDigits: 2 })}{item.value == null ? "" : result.data.value_unit}</Body><Body>Based on {item.entries.toLocaleString()} entries.</Body><Button title="View supporting records" variant="secondary" onPress={() => router.push({ pathname: '/entries/[id]', params: { id, request: JSON.stringify({ kind: 'comparison', comparison: result.data!.plan, evidence_revision: result.data!.evidence_revision, group_value: item.group_value }) } })} /></Card>)}</>}
  </Screen>;
}
