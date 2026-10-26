import { useEffect, useState } from 'react';
import * as Linking from 'expo-linking';
import { router, useLocalSearchParams } from 'expo-router';
import { supabase } from '../../lib/supabase';
import { completeAuthCallback } from '../../lib/auth-callback';
import { messageOf } from '../../lib/api';
import { Body, Button, ErrorNotice, Field, Heading, Loading, Screen } from '../../components/ui';

export default function AuthCallback() {
  const url = Linking.useURL();
  const {
    code, error: callbackError, error_description: errorDescription, type: callbackType,
    access_token: accessToken, refresh_token: refreshToken, '#': hash,
  } = useLocalSearchParams<{
    code?: string;
    error?: string;
    error_description?: string;
    type?: string;
    access_token?: string;
    refresh_token?: string;
    '#': string;
  }>();
  const [error, setError] = useState<string | null>(null);
  const [recovery, setRecovery] = useState(false);
  const [ready, setReady] = useState(false);
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const callbackParams = new URLSearchParams();
    for (const [key, value] of [
      ['code', code], ['error', callbackError], ['error_description', errorDescription],
      ['type', callbackType], ['access_token', accessToken], ['refresh_token', refreshToken],
    ] as const) {
      if (value) callbackParams.set(key, value);
    }
    const routeUrl = callbackParams.toString() || hash
      ? `zephyr://auth/callback?${callbackParams.toString()}${hash ? `#${hash}` : ''}`
      : null;
    const callbackUrl = routeUrl ?? url;
    if (!callbackUrl) {
      const timeout = setTimeout(() => {
        setError('No sign-in response was received. Close this screen and try again.');
        setReady(true);
      }, 10000);
      return () => clearTimeout(timeout);
    }
    let canceled = false;
    async function complete() {
      try {
        const type = await completeAuthCallback(callbackUrl!);
        if (canceled) return;
        if (type === 'recovery') { setRecovery(true); setReady(true); }
        else router.replace('/');
      } catch (failure) { if (!canceled) { setError(messageOf(failure)); setReady(true); } }
    }
    void complete();
    return () => { canceled = true; };
  }, [url, code, callbackError, errorDescription, callbackType, accessToken, refreshToken, hash]);

  async function reset() {
    setBusy(true); setError(null);
    try {
      if (password.length < 8) throw new Error('Use at least 8 characters');
      const { error: failure } = await supabase.auth.updateUser({ password });
      if (failure) throw failure;
      router.replace('/');
    } catch (failure) { setError(messageOf(failure)); } finally { setBusy(false); }
  }
  return <Screen><Heading title={recovery ? 'Choose a new password' : 'Completing sign-in'} />
    {!ready && <Loading label="Checking your sign-in link…" />}
    {error && <ErrorNotice message={error} />}
    {recovery && <><Field label="New password" value={password} onChangeText={setPassword} secureTextEntry autoComplete="new-password" /><Button title="Save password" loading={busy} onPress={() => void reset()} /></>}
    {ready && !recovery && <><Body>Open a fresh confirmation or password reset link on this device.</Body><Button title="Continue" onPress={() => router.replace('/')} /></>}
  </Screen>;
}
