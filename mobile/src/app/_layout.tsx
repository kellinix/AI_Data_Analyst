import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { AuthProvider, useAuth } from '../providers/auth';
import { configurationErrors, isConfigured } from '../lib/config';
import { ApiError } from '../lib/api-core';
import { Body, Card, Heading, Loading, Screen, colors } from '../components/ui';

const queryClient = new QueryClient({ defaultOptions: { queries: {
  staleTime: 20_000,
  retry: (attempt, error) => !(error instanceof ApiError && error.status < 500) && attempt < 2,
}, mutations: { retry: false } } });

function Navigation() {
  const { session, loading } = useAuth();
  if (!isConfigured) return <Screen><Heading title="Set up Zephyr" subtitle="Connect this app to your existing Zephyr server and Supabase project." /><Card><Body>Add these values to mobile/.env, then restart Expo:</Body>{configurationErrors.map((item) => <Body key={item}>{item}</Body>)}</Card><Body>Use the computer’s network address for a physical phone. localhost refers to the phone itself.</Body></Screen>;
  if (loading) return <Screen><Loading label="Opening Zephyr…" /></Screen>;
  return <Stack screenOptions={{ headerTintColor: colors.ink, headerStyle: { backgroundColor: '#fff' }, headerShadowVisible: false, contentStyle: { backgroundColor: colors.canvas } }}>
    <Stack.Screen name="index" options={{ headerShown: false }} />
    <Stack.Protected guard={!session}><Stack.Screen name="sign-in" options={{ headerShown: false }} /></Stack.Protected>
    <Stack.Screen name="auth/callback" options={{ title: 'Account access' }} />
    <Stack.Protected guard={!!session}>
      <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
      <Stack.Screen name="analysis/[id]" options={{ title: 'Analysis' }} />
      <Stack.Screen name="entries/[id]" options={{ title: 'Supporting records' }} />
      <Stack.Screen name="compare/[id]" options={{ title: 'Compare groups' }} />
      <Stack.Screen name="chat/[id]" options={{ title: 'Ask Zephyr' }} />
    </Stack.Protected>
  </Stack>;
}

export default function RootLayout() {
  return <SafeAreaProvider><QueryClientProvider client={queryClient}><AuthProvider><StatusBar style="dark" /><Navigation /></AuthProvider></QueryClientProvider></SafeAreaProvider>;
}
