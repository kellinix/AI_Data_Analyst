import { useState } from 'react';
import { Switch, Text, View } from 'react-native';
import * as DocumentPicker from 'expo-document-picker';
import { router } from 'expo-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Ionicons } from '@expo/vector-icons';
import { api, messageOf } from '../../lib/api';
import { supportedFile, uploadDocument } from '../../lib/files';
import { useAuth } from '../../providers/auth';
import type { Analysis, UploadedFile, UserProfile } from '../../generated/contracts';
import { Body, Button, Card, ErrorNotice, Field, Label, Screen, colors } from '../../components/ui';

export default function Upload() {
  const { session } = useAuth();
  const queryClient = useQueryClient();
  const profile = useQuery({ queryKey: ['profile', session?.user.id], queryFn: ({ signal }) => api<UserProfile>('/users/me', { signal }) });
  const [asset, setAsset] = useState<DocumentPicker.DocumentPickerAsset | null>(null);
  const [uploaded, setUploaded] = useState<UploadedFile | null>(null);
  const [name, setName] = useState('');
  const [context, setContext] = useState('');
  const [clean, setClean] = useState(true);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState('');
  const [error, setError] = useState<string | null>(null);

  async function choose() {
    try {
      const result = await DocumentPicker.getDocumentAsync({ type: '*/*', copyToCacheDirectory: true, multiple: false });
      if (result.canceled) return;
      const file = result.assets[0];
      if (!supportedFile.test(file.name)) throw new Error('Choose a CSV, Excel, JSON, Parquet, or TSV file');
      if (file.size != null && file.size > 512 * 1024 * 1024) throw new Error('Files must be smaller than 512 MB');
      if (file.size != null && profile.data && file.size > profile.data.usage.storage_limit_bytes - profile.data.usage.storage_used_bytes) throw new Error('This file exceeds your remaining storage allowance');
      setAsset(file); setUploaded(null); setProgress(0); setError(null);
      setName(file.name.replace(/\.[^.]+$/, '').replace(/[_-]/g, ' '));
    } catch (failure) { setError(messageOf(failure)); }
  }

  async function create() {
    if (!asset) return;
    setBusy(true); setError(null);
    try {
      setStage(uploaded ? 'Preparing analysis…' : 'Uploading…');
      const file = uploaded ?? await uploadDocument(asset, setProgress);
      setUploaded(file); setStage('Preparing analysis…');
      const analysis = await api<Analysis>('/analyses', { method: 'POST', timeout: 600_000, body: {
        file_id: file.id, name: name.trim() || undefined,
        relationship_context: context.trim() ? { data_description: context.trim(), analysis_mode: 'single' } : undefined,
        cleaning: { mode: clean ? 'clean' : 'raw' },
      } });
      void queryClient.invalidateQueries({ queryKey: ['analyses'] });
      void queryClient.invalidateQueries({ queryKey: ['profile'] });
      setAsset(null); setUploaded(null); setProgress(0); setContext(''); setName('');
      router.push({ pathname: '/analysis/[id]', params: { id: analysis.id } });
    } catch (failure) { setError(messageOf(failure)); } finally { setBusy(false); setStage(''); }
  }

  const quotaFull = profile.data && profile.data.usage.analyses_this_month >= profile.data.usage.analyses_limit;
  return <Screen><View style={{ borderRadius: 28, padding: 24, backgroundColor: '#302056', gap: 10 }}><Text style={{ color: '#B5F3D8', fontSize: 12, fontWeight: '800', letterSpacing: 2 }}>NEW ANALYSIS</Text><Text style={{ color: '#fff', fontSize: 29, fontWeight: '800', letterSpacing: -1 }}>Make sense of your data.</Text><Text style={{ color: '#DDD1F2', fontSize: 14, lineHeight: 22 }}>Choose a spreadsheet from your phone or cloud files.</Text></View>
    <Card><View style={{ width: 54, height: 54, borderRadius: 18, backgroundColor: colors.pale, alignItems: 'center', justifyContent: 'center' }}><Ionicons name="document-text-outline" size={29} color={colors.blue} /></View><Label>{asset?.name ?? 'Choose your file'}</Label><Body>{asset?.size ? `${(asset.size / 1024 / 1024).toFixed(1)} MB` : 'CSV, Excel, JSON, Parquet, or TSV'}</Body><Button title={asset ? 'Choose another file' : 'Browse files'} disabled={busy} variant="secondary" icon="folder-open-outline" onPress={() => void choose()} /></Card>
    {asset && <Card><Field label="Analysis name" value={name} onChangeText={setName} editable={!busy} maxLength={512} /><Field label="What should Zephyr know? (optional)" placeholder="For example: monthly sales by region. Revenue is recorded in GBP." value={context} onChangeText={setContext} multiline maxLength={2000} editable={!busy} />
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}><View style={{ flex: 1 }}><Label>Clean data before analysis</Label><Body>Normalize dates, text, and numeric formats.</Body></View><Switch accessibilityLabel="Clean data before analysis" value={clean} onValueChange={setClean} disabled={busy} trackColor={{ true: colors.blue }} /></View>
      {!clean && <Body>Raw mode preserves the original values; text-formatted dates may prevent forecasting.</Body>}
    </Card>}
    {quotaFull && <ErrorNotice message="You’ve used your monthly analysis allowance. Wait for your next billing cycle or update your plan on the website." />}
    {error && <ErrorNotice message={error} />}
    {busy && <Body>{stage} {progress > 0 && progress < 100 ? `${progress}%` : ''}</Body>}
    <Button title="Create analysis" icon="sparkles-outline" loading={busy} disabled={!asset || !!quotaFull} onPress={() => void create()} />
    {profile.data && <Body>{profile.data.usage.analyses_this_month} of {profile.data.usage.analyses_limit} monthly analyses used.</Body>}
    <Body>Your file is sent to your Zephyr server for processing. Keep this screen open until the analysis starts.</Body>
  </Screen>;
}
