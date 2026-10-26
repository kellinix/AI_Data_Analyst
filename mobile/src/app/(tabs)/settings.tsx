import { useState } from 'react';
import { Alert } from 'react-native';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, messageOf } from '../../lib/api';
import { supabase } from '../../lib/supabase';
import { useAuth } from '../../providers/auth';
import type { UserProfile } from '../../generated/contracts';
import { Body, Button, Card, ErrorNotice, Field, Heading, Label, Loading, Screen } from '../../components/ui';

export default function Settings() {
  const { session } = useAuth();
  const queryClient = useQueryClient();
  const profile = useQuery({ queryKey: ['profile', session?.user.id], queryFn: ({ signal }) => api<UserProfile>('/users/me', { signal }) });
  const [draftName, setDraftName] = useState<string | null>(null);
  const name = draftName ?? profile.data?.full_name ?? '';
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const save = useMutation({ mutationFn: async () => {
    if (name.trim().length < 2) throw new Error('Use at least two characters for your name');
    await api('/users/me', { method: 'PATCH', body: { full_name: name.trim() } });
  }, onSuccess: () => { setNotice('Profile updated'); void queryClient.invalidateQueries({ queryKey: ['profile'] }); }, onError: (failure) => setError(messageOf(failure)) });
  const signOut = useMutation({ mutationFn: async () => {
    const { error: failure } = await supabase.auth.signOut({ scope: 'local' });
    if (failure) throw failure;
  }, onError: (failure) => setError(messageOf(failure)) });
  const remove = useMutation({ mutationFn: async () => {
    await api<void>('/users/me', { method: 'DELETE' });
    await queryClient.cancelQueries();
    queryClient.clear();
    const { error: failure } = await supabase.auth.signOut({ scope: 'local' });
    if (failure) throw new Error('Your account was deleted. Close the app and sign in again to clear this session.');
  }, onError: (failure) => setError(messageOf(failure)) });
  const busy = save.isPending || remove.isPending || signOut.isPending;
  return <Screen><Heading title="Your account" subtitle={session?.user.email} />
    {profile.isPending && <Loading />}{profile.error && <ErrorNotice message={messageOf(profile.error)} retry={() => void profile.refetch()} />}
    {error && <ErrorNotice message={error} />}{notice && <Body>{notice}</Body>}
    {profile.data && <><Card><Field label="Full name" value={name} onChangeText={setDraftName} maxLength={255} editable={!busy} /><Button title="Save profile" loading={save.isPending} disabled={busy} onPress={() => { setError(null); setNotice(null); save.mutate(); }} /></Card>
      <Card><Label>{profile.data.plan.charAt(0).toUpperCase() + profile.data.plan.slice(1)} plan</Label><Body>{profile.data.usage.analyses_this_month} of {profile.data.usage.analyses_limit} monthly analyses used</Body><Body>{profile.data.usage.ai_queries_this_month} of {profile.data.usage.ai_queries_limit} monthly questions used</Body><Body>{(profile.data.usage.storage_used_bytes / 1024 / 1024).toFixed(1)} MB of {(profile.data.usage.storage_limit_bytes / 1024 / 1024).toFixed(0)} MB storage used</Body><Body>Manage your subscription on the website.</Body></Card></>}
    <Button title="Sign out" variant="secondary" disabled={busy} loading={signOut.isPending} onPress={() => signOut.mutate()} />
    <Card><Label>Delete account</Label><Body>This permanently deletes your account, uploaded files, analyses, and chats.</Body><Button title="Delete my account" variant="danger" loading={remove.isPending} disabled={busy} onPress={() => Alert.alert('Permanently delete your account?', 'This removes all your Zephyr data and cannot be undone.', [{ text: 'Keep account', style: 'cancel' }, { text: 'Delete account', style: 'destructive', onPress: () => { setError(null); remove.mutate(); } }])} /></Card>
  </Screen>;
}
