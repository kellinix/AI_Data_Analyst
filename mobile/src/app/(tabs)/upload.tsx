import { useEffect, useRef, useState } from 'react';
import { Switch, Text, View } from 'react-native';
import * as DocumentPicker from 'expo-document-picker';
import { router } from 'expo-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Ionicons } from '@expo/vector-icons';
import { api, messageOf } from '../../lib/api';
import { ApiError } from '../../lib/api-core';
import { uploadDocument } from '../../lib/files';
import { addUploadAssets, analysisUploadRequest, profileUploadQueue, type QueuedDocument } from '../../lib/upload-workflow';
import { generateRelationshipSuggestions } from '../../generated/upload-relationships';
import { useAuth } from '../../providers/auth';
import type { Analysis, UserProfile } from '../../generated/contracts';
import { Body, Button, Card, ErrorNotice, Field, Label, Screen, colors } from '../../components/ui';

export default function Upload() {
  const { session } = useAuth();
  const queryClient = useQueryClient();
  const profile = useQuery({ queryKey: ['profile', session?.user.id], queryFn: ({ signal }) => api<UserProfile>('/users/me', { signal }) });
  const [queue, setQueue] = useState<QueuedDocument[]>([]);
  const [name, setName] = useState('');
  const [context, setContext] = useState('');
  const [instructions, setInstructions] = useState('');
  const [clean, setClean] = useState(true);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [creationUncertain, setCreationUncertain] = useState(false);
  const operationActive = useRef(false);
  const activeAccount = useRef(session?.user.id);
  useEffect(() => {
    activeAccount.current = session?.user.id;
    return () => { activeAccount.current = undefined; };
  }, [session?.user.id]);

  const uploadedFiles = queue.flatMap(item => item.uploaded ? [item.uploaded] : []);
  const ready = queue.length > 0 && uploadedFiles.length === queue.length;
  const suggestions = ready ? generateRelationshipSuggestions(uploadedFiles) : [];
  const quotaFull = !!profile.data && profile.data.usage.analyses_this_month >= profile.data.usage.analyses_limit;

  async function choose() {
    if (operationActive.current) return;
    operationActive.current = true;
    setBusy(true);
    setStage('Selecting files…');
    try {
      const result = await DocumentPicker.getDocumentAsync({ type: '*/*', copyToCacheDirectory: true, multiple: true });
      if (result.canceled) return;
      const remaining = profile.data && profile.data.usage.storage_limit_bytes - profile.data.usage.storage_used_bytes;
      const next = addUploadAssets(queue, result.assets, remaining);
      setQueue(next);
      setProgress(0);
      setError(null);
      if (queue.length === 0) {
        setCreationUncertain(false);
        setName(next.length === 1 ? next[0].asset.name.replace(/\.[^.]+$/, '').replace(/[_-]/g, ' ') : 'Combined analysis');
      } else if (queue.length === 1 && next.length > 1 && name === queue[0].asset.name.replace(/\.[^.]+$/, '').replace(/[_-]/g, ' ')) {
        setName('Combined analysis');
      }
    } catch (failure) {
      setError(messageOf(failure));
    } finally {
      operationActive.current = false;
      setBusy(false);
      setStage('');
    }
  }

  async function prepare() {
    if (operationActive.current || queue.length === 0) return;
    operationActive.current = true;
    setBusy(true);
    setError(null);
    const accountId = session?.user.id;
    try {
      await profileUploadQueue(queue, (asset, onProgress) => {
        if (!accountId || activeAccount.current !== accountId) throw new Error('Sign in again before uploading more files');
        return uploadDocument(asset, onProgress);
      }, (id, value) => {
        if (activeAccount.current !== accountId) return;
        setStage(`Uploading ${queue.find(item => item.id === id)!.asset.name}…`);
        setProgress(value);
      }, (id, file) => {
        if (activeAccount.current !== accountId) throw new Error('Your account changed. Sign in again before continuing.');
        setQueue(current => current.map(item => item.id === id ? { ...item, uploaded: file } : item));
      });
    } catch (failure) {
      setError(messageOf(failure));
    } finally {
      void queryClient.invalidateQueries({ queryKey: ['profile'] });
      operationActive.current = false;
      setBusy(false);
      setStage('');
    }
  }

  async function create() {
    if (operationActive.current || !ready || quotaFull || creationUncertain) return;
    operationActive.current = true;
    setBusy(true);
    setError(null);
    setStage('Preparing analysis…');
    try {
      const request = analysisUploadRequest(uploadedFiles, name, context, instructions, clean);
      const analysis = await api<Analysis>(request.path, { method: 'POST', timeout: 600_000, body: request.body });
      void queryClient.invalidateQueries({ queryKey: ['analyses'] });
      void queryClient.invalidateQueries({ queryKey: ['profile'] });
      setQueue([]);
      setProgress(0);
      setContext('');
      setInstructions('');
      setName('');
      router.push({ pathname: '/analysis/[id]', params: { id: analysis.id } });
    } catch (failure) {
      const uncertain = !(failure instanceof ApiError) || failure.status >= 500;
      setCreationUncertain(uncertain);
      setError(uncertain ? 'The server may have started this analysis. Check Analyses before submitting these files again.' : messageOf(failure));
    } finally {
      operationActive.current = false;
      setBusy(false);
      setStage('');
    }
  }

  return <Screen>
    <View style={{ borderRadius: 28, padding: 24, backgroundColor: '#302056', gap: 10 }}>
      <Text style={{ color: '#B5F3D8', fontSize: 12, fontWeight: '800', letterSpacing: 2 }}>NEW ANALYSIS</Text>
      <Text style={{ color: '#fff', fontSize: 29, fontWeight: '800', letterSpacing: -1 }}>Make sense of your data.</Text>
      <Text style={{ color: '#DDD1F2', fontSize: 14, lineHeight: 22 }}>Choose spreadsheets from your phone or cloud files, then review how they relate.</Text>
    </View>
    <Card>
      <View style={{ width: 54, height: 54, borderRadius: 18, backgroundColor: colors.pale, alignItems: 'center', justifyContent: 'center' }}>
        <Ionicons name="documents-outline" size={29} color={colors.blue} />
      </View>
      <Label>{queue.length ? `${queue.length} ${queue.length === 1 ? 'file' : 'files'} selected` : 'Choose your files'}</Label>
      <Body>CSV, Excel, JSON, Parquet, or TSV. Up to 512 MB per file.</Body>
      <Button title={queue.length ? 'Add more files' : 'Browse files'} disabled={busy} variant="secondary" icon="folder-open-outline" onPress={() => void choose()} />
    </Card>
    {queue.map(item => <Card key={item.id}>
      <Label>{item.asset.name}</Label>
      <Body>{item.asset.size != null ? `${(item.asset.size / 1024 / 1024).toFixed(1)} MB` : 'Size checked during upload'}</Body>
      {item.uploaded ? <Body>{item.uploaded.row_count ?? 'Unknown'} rows · {item.uploaded.column_count ?? 'Unknown'} columns · Ready</Body> : <Body>Waiting to upload and profile</Body>}
      <Button title={`Remove ${item.asset.name}`} disabled={busy} variant="secondary" onPress={() => setQueue(current => current.filter(file => file.id !== item.id))} />
    </Card>)}
    {queue.length > 0 && <Card>
      <Field label="Analysis name" value={name} onChangeText={setName} editable={!busy} maxLength={512} />
      <Field label="What should Vesquiri know? (optional)" placeholder="For example, monthly sales by region. Revenue is recorded in GBP." value={context} onChangeText={setContext} multiline maxLength={2000} editable={!busy} />
      <Field label="Analysis instructions (optional)" placeholder="Describe related records, periods to compare, or questions to investigate." value={instructions} onChangeText={setInstructions} multiline maxLength={4000} editable={!busy} />
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
        <View style={{ flex: 1 }}><Label>Clean data before analysis</Label><Body>Normalize dates, text, and numeric formats.</Body></View>
        <Switch accessibilityLabel="Clean data before analysis" value={clean} onValueChange={setClean} disabled={busy} trackColor={{ true: colors.blue }} />
      </View>
      {!clean && <Body>Raw mode preserves the original values. Text-formatted dates may prevent forecasting.</Body>}
    </Card>}
    {ready && <Card>
      <Label>Automatic relationship suggestions</Label>
      <Body>Suggestions use your uploaded column profiles. Review them before starting analysis.</Body>
      {suggestions.map(suggestion => <View key={suggestion.id} style={{ gap: 8, borderTopWidth: 1, borderTopColor: colors.line, paddingTop: 14 }}>
        <Label>{suggestion.title}</Label>
        <Body>{suggestion.description}</Body>
        <Body>{Math.round(suggestion.confidence * 100)}% confidence · {suggestion.files.join(', ')}</Body>
        {suggestion.columns.length > 0 && <Body>{suggestion.columns.join(' · ')}</Body>}
      </View>)}
      {queue.length > 1 && <Body>These files will form one combined analysis with their source rows preserved, using the same workflow as the website.</Body>}
    </Card>}
    {quotaFull && <ErrorNotice message="You’ve used your analysis allowance for this month. You can create more analyses next month." />}
    {error && <ErrorNotice message={error} />}
    {busy && <Body>{stage} {progress > 0 && progress < 100 ? `${progress}%` : ''}</Body>}
    {creationUncertain
      ? <Button title="Check Analyses" variant="secondary" onPress={() => router.push('/(tabs)')} />
      : ready
        ? <Button title="Create analysis" icon="sparkles-outline" loading={busy} disabled={quotaFull} onPress={() => void create()} />
        : <Button title="Upload and review files" icon="cloud-upload-outline" loading={busy} disabled={queue.length === 0} onPress={() => void prepare()} />}
    {profile.data && <Body>{profile.data.usage.analyses_this_month} of {profile.data.usage.analyses_limit} monthly analyses used.</Body>}
    <Body>Your files are sent to your Vesquiri server for processing. Keep this screen open until the analysis starts.</Body>
  </Screen>;
}
