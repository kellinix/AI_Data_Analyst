import { createApi } from './api-core';
import { config } from './config';
import { supabase } from './supabase';

export async function accessToken() {
  const { data, error } = await supabase.auth.getSession();
  if (error) throw error;
  return data.session?.access_token ?? null;
}
export const api = createApi(config.apiUrl, accessToken);
export const messageOf = (error: unknown) => error instanceof Error ? error.message : 'Something went wrong. Please retry.';
