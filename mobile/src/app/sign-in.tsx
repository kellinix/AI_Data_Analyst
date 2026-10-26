import { useEffect, useState } from 'react';
import { Keyboard, Platform, View, Text } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as Linking from 'expo-linking';
import * as WebBrowser from 'expo-web-browser';
import { supabase } from '../lib/supabase';
import { messageOf } from '../lib/api';
import { completeAuthCallback } from '../lib/auth-callback';
import { useAuth } from '../providers/auth';
import { Body, Button, Card, ErrorNotice, Field, Heading, Screen, colors } from '../components/ui';

// Keep native Auth redirects stable in development builds as well as releases.
const authCallbackUrl = Platform.OS === 'web' ? Linking.createURL('auth/callback') : 'zephyr://auth/callback';

export default function SignIn() {
  const [mode, setMode] = useState<'login' | 'register' | 'reset'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [keyboardVisible, setKeyboardVisible] = useState(false);
  const auth = useAuth();

  useEffect(() => {
    const shown = Keyboard.addListener('keyboardDidShow', () => setKeyboardVisible(true));
    const hidden = Keyboard.addListener('keyboardDidHide', () => setKeyboardVisible(false));
    return () => { shown.remove(); hidden.remove(); };
  }, []);

  async function submit() {
    setError(null); setNotice(null); setBusy(true);
    try {
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) throw new Error('Enter a valid email address');
      if (mode !== 'reset' && !password) throw new Error('Enter your password');
      if (mode === 'register' && (password.length < 8 || name.trim().length < 2)) throw new Error('Enter your name and a password with at least 8 characters');
      if (mode === 'login') {
        const result = await supabase.auth.signInWithPassword({ email: email.trim(), password });
        if (result.error) throw result.error;
      } else if (mode === 'register') {
        const result = await supabase.auth.signUp({ email: email.trim(), password, options: {
          data: { full_name: name.trim() }, emailRedirectTo: authCallbackUrl,
        } });
        if (result.error) throw result.error;
        if (!result.data.session) setNotice('Check your email to confirm your account, then sign in.');
      } else {
        const result = await supabase.auth.resetPasswordForEmail(email.trim(), { redirectTo: `${authCallbackUrl}?type=recovery` });
        if (result.error) throw result.error;
        setNotice('If an account exists for this email, a password reset link is on its way.');
      }
    } catch (failure) { setError(messageOf(failure)); } finally { setBusy(false); }
  }

  async function signInWithGoogle() {
    setError(null); setNotice(null); setBusy(true);
    try {
      const redirectTo = authCallbackUrl;
      const { data, error: failure } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: { redirectTo, skipBrowserRedirect: Platform.OS !== 'web' },
      });
      if (failure) throw failure;
      if (Platform.OS !== 'web') {
        if (!data.url) throw new Error('Google sign-in could not start. Try again.');
        const result = await WebBrowser.openAuthSessionAsync(
          data.url,
          redirectTo,
          Platform.OS === 'android' ? { createTask: false } : undefined,
        );
        if (result.type === 'success') await completeAuthCallback(result.url);
      }
    } catch (failure) { setError(messageOf(failure)); } finally { setBusy(false); }
  }

  const switchMode = (next: typeof mode) => { setMode(next); setError(null); setNotice(null); setPassword(''); };
  return <SafeAreaView style={{ flex: 1, backgroundColor: colors.canvas }} edges={['top']}><Screen keyboardAvoidingBehavior={Platform.OS === 'android' ? 'height' : undefined}>
    {!keyboardVisible && <View style={{ padding: 24, borderRadius: 28, backgroundColor: '#302056', gap: 14, overflow: 'hidden' }}>
      <View style={{ position: 'absolute', width: 160, height: 160, borderRadius: 80, right: -55, top: -75, backgroundColor: '#6445A6' }} />
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}><Ionicons name="analytics" color="#B5F3D8" size={28} /><Text style={{ fontSize: 23, fontWeight: '800', color: '#fff' }}>Zephyr.</Text></View>
      <Text style={{ fontSize: 29, lineHeight: 35, fontWeight: '800', letterSpacing: -1, color: '#fff' }}>Your data. Clear decisions.</Text>
      <Text style={{ fontSize: 14, lineHeight: 22, color: '#DDD1F2' }}>Upload a spreadsheet and carry your insights with you.</Text>
    </View>}
    <Card><Heading title={mode === 'login' ? 'Welcome back' : mode === 'register' ? 'Create your account' : 'Reset your password'} />
      {mode !== 'reset' && <Button title="Continue with Google" variant="secondary" disabled={busy} onPress={() => void signInWithGoogle()} />}
      {mode === 'register' && <Field label="Full name" value={name} onChangeText={setName} autoComplete="name" editable={!busy} />}
      <Field label="Email" value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none" autoComplete="email" editable={!busy} />
      {mode !== 'reset' && <Field label="Password" value={password} onChangeText={setPassword} secureTextEntry autoCapitalize="none" autoComplete={mode === 'register' ? 'new-password' : 'current-password'} editable={!busy} onSubmitEditing={() => void submit()} />}
      {(error || auth.error) && <ErrorNotice message={error || auth.error!} />}
      {notice && <Body>{notice}</Body>}
      <Button title={mode === 'login' ? 'Sign in' : mode === 'register' ? 'Create account' : 'Send reset link'} loading={busy} onPress={() => void submit()} />
      <Button title={mode === 'login' ? 'Create an account' : 'Back to sign in'} variant="secondary" disabled={busy} onPress={() => switchMode(mode === 'login' ? 'register' : 'login')} />
      {mode === 'login' && <Button title="Forgot password?" variant="secondary" disabled={busy} onPress={() => switchMode('reset')} />}
    </Card>
    <Body>Your existing website account works here too.</Body>
  </Screen></SafeAreaView>;
}
