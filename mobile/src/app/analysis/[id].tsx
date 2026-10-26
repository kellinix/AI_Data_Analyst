import { useState } from 'react';
import { Alert, Share, Text, View } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, messageOf } from '../../lib/api';
import { exportReport } from '../../lib/files';
import { count, fieldLabel, formatMetric } from '../../lib/format';
import { useAuth } from '../../providers/auth';
import type { Analysis, EvidenceEntryRequest, Insight, ShareLinkResponse } from '../../generated/contracts';
import { Chart } from '../../components/chart';
import { Badge, Body, Button, Card, ErrorNotice, Label, Loading, Screen, colors } from '../../components/ui';

export default function AnalysisScreen() {
  const { id: parameter } = useLocalSearchParams<{ id: string }>();
  const id = Array.isArray(parameter) ? parameter[0] : parameter;
  const { session } = useAuth();
  const queryClient = useQueryClient();
  const [actionError, setActionError] = useState<string | null>(null);
  const [exporting, setExporting] = useState<string | null>(null);
  const [showSummaryEvidence, setShowSummaryEvidence] = useState(false);
  const [showQualityDetails, setShowQualityDetails] = useState(false);
  const result = useQuery({
    queryKey: ['analysis', session?.user.id, id],
    queryFn: ({ signal }) => api<Analysis>(`/analyses/${encodeURIComponent(id)}`, { signal }),
    refetchInterval: (query) => ['pending', 'processing'].includes(query.state.data?.status ?? '') ? 2000 : false,
  });
  const status = useQuery({
    queryKey: ['analysis-status', session?.user.id, id],
    queryFn: ({ signal }) => api<{ progress: number; status: string; error?: string }>(`/analyses/${encodeURIComponent(id)}/status`, { signal }),
    enabled: ['pending', 'processing'].includes(result.data?.status ?? ''),
    refetchInterval: 2000,
  });
  const share = useMutation({ mutationFn: async () => {
    const link = await api<ShareLinkResponse>(`/analyses/${id}/share`, { method: 'POST' });
    if (!/^https?:\/\//i.test(link.share_url)) throw new Error('The server returned an invalid share link');
    await Share.share({ message: `${result.data?.name ?? 'Zephyr analysis'}\n${link.share_url}` });
  }, onError: (error) => setActionError(messageOf(error)) });
  const remove = useMutation({ mutationFn: () => api<void>(`/analyses/${id}`, { method: 'DELETE' }), onSuccess: () => {
    queryClient.removeQueries({ queryKey: ['analysis', session?.user.id, id] });
    void queryClient.invalidateQueries({ queryKey: ['analyses'] });
    void queryClient.invalidateQueries({ queryKey: ['profile'] });
    router.replace('/(tabs)');
  }, onError: (error) => setActionError(messageOf(error)) });
  const rerun = useMutation({ mutationFn: () => api<Analysis>(`/analyses/${id}/rerun`, { method: 'POST', timeout: 600_000 }), onSuccess: (analysis) => {
    queryClient.setQueryData(['analysis', session?.user.id, id], analysis);
    void queryClient.invalidateQueries({ queryKey: ['analyses'] });
  }, onError: (error) => setActionError(messageOf(error)) });
  const refreshSummary = useMutation({ mutationFn: () => api(`/analyses/${id}/summary/refresh`, { method: 'POST' }), onSuccess: () => {
    void queryClient.invalidateQueries({ queryKey: ['analysis', session?.user.id, id] });
  }, onError: (error) => setActionError(messageOf(error)) });

  async function download(format: 'pdf' | 'excel') {
    setExporting(format); setActionError(null);
    try { await exportReport(id, format); } catch (failure) { setActionError(messageOf(failure)); } finally { setExporting(null); }
  }
  if (result.isPending) return <Screen><Loading label="Opening your analysis…" /></Screen>;
  if (!result.data) return <Screen><ErrorNotice message={messageOf(result.error)} retry={() => void result.refetch()} /></Screen>;
  const analysis = result.data;
  const summaryChecks = (analysis.metadata?.analysis_evidence as {
    summary_checks?: { method?: string; facts?: { id: string; text: string; calculation: string; scope: string }[] };
  } | undefined)?.summary_checks;
  const summaryFacts = summaryChecks?.method === 'measured_facts_v1' &&
    summaryChecks.facts?.map((fact) => fact.text).join('\n') === analysis.summary
    ? summaryChecks.facts : [];
  const running = ['pending', 'processing'].includes(analysis.status);
  const recordContext = analysis.metadata?.record_context as { description?: string } | undefined;
  const insights = analysis.insights ?? [];
  const quality = analysis.metadata?.data_quality as { headline?: string; score_explanation?: string; score?: number; scope?: string; empty_fields?: string[]; scoring_method?: string; issues?: { description?: string; message?: string; column?: string; column_label?: string; evidence_link?: EvidenceEntryRequest }[]; source_quality?: { score?: number; scope?: string; issues?: { column?: string; description?: string }[] } } | undefined;
  const evidence = analysis.metadata?.analysis_evidence as { entity_counts?: { column: string; distinct_values: number; count_basis: string }[]; limitations?: string[]; cleaning?: { input_rows: number; output_rows: number; row_changes?: { reason: string; rows: number }[]; reconciled: boolean } } | undefined;
  return <Screen><View style={{ borderRadius: 28, backgroundColor: '#302056', padding: 24, gap: 12, overflow: 'hidden' }}>
    <View style={{ position: 'absolute', width: 170, height: 170, borderRadius: 85, right: -48, top: -86, backgroundColor: '#6042A4' }} />
    <Text style={{ color: '#B5F3D8', fontSize: 12, fontWeight: '800', letterSpacing: 2 }}>ANALYSIS REPORT</Text>
    <Text style={{ color: '#fff', fontSize: 27, fontWeight: '800', letterSpacing: -0.7 }}>{analysis.name}</Text>
    <Text style={{ color: '#DDD1F2', fontSize: 13 }}>{analysis.filename} · {count(analysis.row_count)} rows</Text>
    <Badge status={analysis.status} />
  </View>
    {result.error && <ErrorNotice message={messageOf(result.error)} retry={() => void result.refetch()} />}
    {running && status.error && <ErrorNotice message={messageOf(status.error)} retry={() => void status.refetch()} />}
    {actionError && <ErrorNotice message={actionError} />}
    {running && <Card><Loading label={`Preparing your dashboard${status.data ? ` · ${status.data.progress}%` : ''}`} /><Body>You can return to your analyses while the server works.</Body></Card>}
    {analysis.status === 'failed' && <Card><ErrorNotice message={analysis.error_message || 'This analysis could not be completed.'} /><Button title="Try analysis again" loading={rerun.isPending} onPress={() => rerun.mutate()} /></Card>}
    {analysis.status === 'completed' && <>
      {recordContext?.description && <Card><Label>What this data is about</Label><Body>{recordContext.description}</Body></Card>}
      <Button title="Ask a question about this data" icon="chatbubble-ellipses-outline" onPress={() => router.push({ pathname: '/chat/[id]', params: { id } })} />
      <Button title="Compare groups" variant="secondary" icon="stats-chart-outline" onPress={() => router.push({ pathname: '/compare/[id]', params: { id } })} />
      {analysis.summary && <View style={{ borderRadius: 24, borderWidth: 1, borderColor: '#DCD0F5', backgroundColor: '#F1EAFE', padding: 21, gap: 11 }}><View style={{ flexDirection: 'row', alignItems: 'center', gap: 9 }}><View style={{ width: 34, height: 34, borderRadius: 11, backgroundColor: colors.blue, alignItems: 'center', justifyContent: 'center' }}><Text style={{ color: '#fff', fontSize: 20 }}>✦</Text></View><Label>The story at a glance</Label></View><Body>{analysis.summary}</Body></View>}
      {!!summaryFacts?.length && <Card><Button title={showSummaryEvidence ? 'Hide explanation' : 'See how we worked this out'} variant="secondary" onPress={() => setShowSummaryEvidence((shown) => !shown)} />
        {showSummaryEvidence && summaryFacts.map((fact, index) => <Body key={fact.id}>{index + 1}. {fact.calculation}. Scope: {fact.scope}.</Body>)}
      </Card>}
      {!summaryFacts?.length && <Card><Body>Update this summary using its saved calculations. This does not run a new analysis.</Body><Button title="Update summary from saved results" variant="secondary" loading={refreshSummary.isPending} onPress={() => refreshSummary.mutate()} /></Card>}
      {evidence && <Card><Label>What these results cover</Label>
        {(evidence.entity_counts ?? []).map((item) => <Body key={item.column}>{item.column}: {count(item.distinct_values)} different values. {item.count_basis}</Body>)}
        {(evidence.limitations ?? []).map((note, index) => <Body key={index}>{note}</Body>)}
        {(evidence.cleaning?.row_changes ?? []).map((change, index) => <Body key={`change-${index}`}>{change.reason}: {count(change.rows)} records.</Body>)}
      </Card>}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
        {insights.filter((item) => item.type === 'summary').map((item, index) => <View key={item.id} style={{ width: '48%', flexGrow: 1 }}><Card><View style={{ width: 30, height: 5, borderRadius: 4, backgroundColor: [colors.blue, colors.teal, colors.coral, colors.gold][index % 4] }} /><Body>{item.title}</Body><Text selectable style={{ color: colors.ink, fontWeight: '800', fontSize: 28 }}>{formatMetric(item)}</Text><Body>{item.description}</Body></Card></View>)}
      </View>
      {!!analysis.charts?.length && <View style={{ gap: 4 }}><Text style={{ color: colors.blue, fontSize: 11, fontWeight: '800', letterSpacing: 2 }}>VISUAL EXPLORATION</Text><Text style={{ color: colors.ink, fontSize: 23, fontWeight: '800' }}>Explore the patterns</Text></View>}
      {(analysis.charts ?? []).map((chart, index) => <Chart key={chart.id} chart={chart} defaultExpanded={index === 0} />)}
      {insights.filter((item) => !['summary', 'recommendation'].includes(item.type)).map((item) => <Card key={item.id}><Badge status={({ forecast: 'Looking ahead', anomaly: 'Worth a closer look', trend: 'How things are changing', correlation: 'Figures that move together', distribution: 'How entries are spread' } as Record<string, string>)[item.type] ?? 'What stands out'} /><Label>{item.title}</Label><Body>{item.description}</Body>{!!item.data?.evidence_link && <SupportingEntries analysisId={id} request={item.data.evidence_link as unknown as EvidenceEntryRequest} />}</Card>)}
      {insights.some((item) => item.type === 'recommendation') && <Label>What to do next</Label>}
      {insights.filter((item) => item.type === 'recommendation').map((item) => <Recommendation key={item.id} insight={item} analysisId={id} />)}
      {quality && <Card><Label>What to check in your file</Label><Label>{quality.headline ?? 'Review these checks before making decisions'}</Label><Body>{quality.scope ?? 'We checked for blanks, repeated entries and unusual numbers. These checks cannot confirm that every entry is correct.'}</Body>
        {!!quality.empty_fields?.length && <Body>Completely blank fields: {quality.empty_fields.join(', ')}. Check whether you need them.</Body>}
        {(quality.issues ?? []).slice(0, 6).map((issue, index) => <View key={index} style={{ gap: 8 }}><Body>{issue.column_label ? `${issue.column_label}: ` : issue.column ? `${issue.column.replaceAll('_', ' ')}: ` : ''}{issue.description ?? issue.message ?? 'Review this field on the website'}</Body>{issue.evidence_link && <SupportingEntries analysisId={id} request={issue.evidence_link} title="View affected records" />}</View>)}
        {quality.source_quality && <><Label>Your original file</Label><Body>{quality.source_quality.scope}</Body>{(quality.source_quality.issues ?? []).map((issue, index) => <Body key={`source-${index}`}>{issue.column}: {issue.description}</Body>)}</>}
        <Button title={showQualityDetails ? 'Hide check details' : 'See check details'} variant="secondary" onPress={() => setShowQualityDetails((shown) => !shown)} />
        {showQualityDetails && <><Body>File check score: {quality.score ?? 'Not available'}/100</Body><Body>{quality.score_explanation ?? quality.scoring_method}</Body></>}
      </Card>}
      <Card><Label>Take your insights with you</Label><Button title="Export PDF" variant="secondary" loading={exporting === 'pdf'} disabled={exporting !== null} icon="document-outline" onPress={() => void download('pdf')} /><Button title="Export Excel" variant="secondary" loading={exporting === 'excel'} disabled={exporting !== null} icon="grid-outline" onPress={() => void download('excel')} /><Button title="Share analysis link" variant="secondary" loading={share.isPending} icon="share-outline" onPress={() => share.mutate()} /><Body>Creating a share link lets anyone with that link view this analysis.</Body></Card>
    </>}
    <Button title="Refresh analysis" variant="secondary" loading={result.isRefetching} onPress={() => void result.refetch()} />
    <Button title="Delete analysis" variant="danger" loading={remove.isPending} disabled={running} onPress={() => Alert.alert('Delete this analysis?', 'This permanently removes its dashboard and chat history.', [{ text: 'Keep analysis', style: 'cancel' }, { text: 'Delete', style: 'destructive', onPress: () => remove.mutate() }])} />
  </Screen>;
}

function Recommendation({ insight, analysisId }: { insight: Insight; analysisId: string }) {
  const [showFigures, setShowFigures] = useState(false);
  const supporting = insight.data?.supporting_figures as { basis: string; figures: { label: string; value: number | null }[]; context: Record<string, string> } | undefined;
  const { session } = useAuth();
  const queryClient = useQueryClient();
  const feedback = useMutation({ mutationFn: (verdict: 'helpful' | 'not_helpful') => api(`/analyses/${analysisId}/insights/${insight.id}/feedback`, {
    method: verdict === insight.user_feedback ? 'DELETE' : 'PUT', body: verdict === insight.user_feedback ? undefined : { verdict },
  }), onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['analysis', session?.user.id, analysisId] }) });
  return <Card><Badge status={insight.importance === 'high' || insight.importance === 'critical' ? 'Check first' : insight.importance === 'low' ? 'For reference' : 'Worth reviewing'} /><Label>{insight.title}</Label><Body>{insight.description}</Body>
    {typeof insight.data?.evidence === 'string' && insight.data.evidence && <><Label>What we found</Label><Body>{insight.data.evidence}</Body></>}
    {typeof insight.data?.expected_impact === 'string' && insight.data.expected_impact && <><Label>Why this helps</Label><Body>{insight.data.expected_impact}</Body></>}
    {supporting && <><Button title={showFigures ? 'Hide supporting figures' : 'See figures behind this action'} variant="secondary" onPress={() => setShowFigures((shown) => !shown)} />{showFigures && <><Body>{supporting.basis}</Body>{supporting.figures.map((figure) => <Body key={figure.label}>{fieldLabel(figure.label)}: {figure.value == null ? 'Not available' : figure.value.toLocaleString(undefined, { maximumFractionDigits: 2 })}</Body>)}{Object.entries(supporting.context).map(([field, value]) => <Body key={field}>{fieldLabel(field)}: {value}</Body>)}</>}</>}
    {!!insight.data?.evidence_link && <SupportingEntries analysisId={analysisId} request={insight.data.evidence_link as unknown as EvidenceEntryRequest} />}
    <Body>Was this recommendation useful?</Body><View style={{ flexDirection: 'row', gap: 10 }}>
    <View style={{ flex: 1 }}><Button title={insight.user_feedback === 'helpful' ? 'Helpful ✓' : 'Helpful'} variant="secondary" disabled={feedback.isPending} onPress={() => feedback.mutate('helpful')} /></View>
    <View style={{ flex: 1 }}><Button title={insight.user_feedback === 'not_helpful' ? 'Not helpful ✓' : 'Not helpful'} variant="secondary" disabled={feedback.isPending} onPress={() => feedback.mutate('not_helpful')} /></View>
  </View>{feedback.error && <ErrorNotice message={messageOf(feedback.error)} />}</Card>;
}

function SupportingEntries({ analysisId, request, title = 'View supporting records' }: { analysisId: string; request: EvidenceEntryRequest; title?: string }) {
  return <Button title={title} variant="secondary" onPress={() => router.push({ pathname: '/entries/[id]', params: { id: analysisId, request: JSON.stringify(request) } })} />;
}
