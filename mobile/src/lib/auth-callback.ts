import { supabase } from './supabase';

let lastCallbackKey: string | null = null;
let lastCompletion: Promise<string | null> | null = null;

// The auth browser and Expo Router can both receive the same native deep link.
// Exchange its one-time PKCE code once, even if both handlers run.
export function completeAuthCallback(url: string): Promise<string | null> {
  const parsed = new URL(url);
  const params = new URLSearchParams(parsed.search);
  new URLSearchParams(parsed.hash.slice(1)).forEach((value, key) => params.set(key, value));
  const callbackKey = params.get('code') ? `code:${params.get('code')}` : url;
  if (callbackKey === lastCallbackKey && lastCompletion) return lastCompletion;
  lastCallbackKey = callbackKey;
  lastCompletion = (async () => {
    if (params.has('error')) {
      throw new Error(params.get('error_description') ?? 'Sign-in was cancelled. Try again.');
    }
    const code = params.get('code');
    const access = params.get('access_token');
    if (code) {
      const { error } = await supabase.auth.exchangeCodeForSession(code);
      if (error) throw error;
    } else if (access && params.get('refresh_token')) {
      const { error } = await supabase.auth.setSession({
        access_token: access,
        refresh_token: params.get('refresh_token')!,
      });
      if (error) throw error;
    } else {
      throw new Error('This sign-in link is incomplete. Try again.');
    }
    return params.get('type');
  })();
  return lastCompletion;
}
