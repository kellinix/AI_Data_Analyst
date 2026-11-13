import { useEffect, useRef, useState } from 'react';
import { View } from 'react-native';
import * as AppleAuthentication from 'expo-apple-authentication';
import * as Crypto from 'expo-crypto';
import { supabase } from '../lib/supabase';
import { messageOf } from '../lib/api';
import { performAppleSignIn } from '../lib/apple-sign-in';

export function AppleSignInButton({ busy, setBusy, onError }: { busy: boolean; setBusy: (busy: boolean) => void; onError: (error: string | null) => void }) {
  const [available, setAvailable] = useState(false);
  const active = useRef(false);
  useEffect(() => { let mounted = true; void AppleAuthentication.isAvailableAsync().then(value => { if (mounted) setAvailable(value); }).catch(() => {}); return () => { mounted = false; }; }, []);
  async function signIn() {
    if (busy || active.current) return;
    active.current = true; setBusy(true); onError(null);
    try {
      await performAppleSignIn({
        random: () => Crypto.randomUUID(),
        sha256: value => Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, value),
        authorize: (nonce, state) => AppleAuthentication.signInAsync({ nonce, state, requestedScopes: [AppleAuthentication.AppleAuthenticationScope.EMAIL] }),
        exchange: (token, nonce) => supabase.auth.signInWithIdToken({ provider: 'apple', token, nonce }),
      });
    } catch (error) {
      if (!(error && typeof error === 'object' && 'code' in error && error.code === 'ERR_REQUEST_CANCELED')) onError(messageOf(error));
    } finally { active.current = false; setBusy(false); }
  }
  if (!available) return null;
  return <View pointerEvents={busy ? 'none' : 'auto'} accessibilityElementsHidden={busy} style={{ opacity: busy ? 0.5 : 1 }}>
    <AppleAuthentication.AppleAuthenticationButton buttonType={AppleAuthentication.AppleAuthenticationButtonType.CONTINUE} buttonStyle={AppleAuthentication.AppleAuthenticationButtonStyle.BLACK} cornerRadius={14} style={{ width: '100%', height: 54 }} onPress={() => void signIn()} />
  </View>;
}
