import { createContext, useContext, useEffect, useState, type PropsWithChildren } from 'react';
import { AppState, Platform } from 'react-native';
import { useQueryClient, focusManager } from '@tanstack/react-query';
import type { Session } from '@supabase/supabase-js';
import { supabase } from '../lib/supabase';
import { isConfigured } from '../lib/config';
import { messageOf } from '../lib/api';

const AuthContext = createContext<{ session: Session | null; loading: boolean; error: string | null }>({ session: null, loading: true, error: null });
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }: PropsWithChildren) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(isConfigured);
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  useEffect(() => {
    if (!isConfigured) return;
    let alive = true;
    let changed = false;
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, next) => {
      changed = true;
      if (!alive) return;
      if (event === 'SIGNED_OUT') {
        void queryClient.cancelQueries();
        queryClient.clear();
      }
      setSession(next);
      setLoading(false);
    });
    supabase.auth.getSession().then(({ data, error: failure }) => {
      if (!alive) return;
      if (failure) setError(failure.message);
      if (!changed) setSession(data.session);
    }).catch((failure) => { if (alive) setError(messageOf(failure)); })
      .finally(() => { if (alive) setLoading(false); });
    const update = (state: string) => {
      const active = state === 'active';
      if (Platform.OS !== 'web') focusManager.setFocused(active);
      if (active) supabase.auth.startAutoRefresh(); else supabase.auth.stopAutoRefresh();
    };
    update(AppState.currentState);
    const listener = AppState.addEventListener('change', update);
    return () => { alive = false; subscription.unsubscribe(); listener.remove(); supabase.auth.stopAutoRefresh(); };
  }, [queryClient]);
  return <AuthContext.Provider value={{ session, loading, error }}>{children}</AuthContext.Provider>;
}
