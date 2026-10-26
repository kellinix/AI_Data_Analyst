import 'react-native-url-polyfill/auto';
import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';
import { createClient } from '@supabase/supabase-js';
import { config } from './config';
import { chunkedStorage, type KeyValueStore } from './secure-storage';

const browserStorage: KeyValueStore = {
  async getItem(key) { return typeof localStorage === 'undefined' ? null : localStorage.getItem(key); },
  async setItem(key, value) { if (typeof localStorage !== 'undefined') localStorage.setItem(key, value); },
  async removeItem(key) { if (typeof localStorage !== 'undefined') localStorage.removeItem(key); },
};
const nativeStorage = chunkedStorage({
  getItem: SecureStore.getItemAsync,
  setItem: (key, value) => SecureStore.setItemAsync(key, value, { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY }),
  removeItem: SecureStore.deleteItemAsync,
});

// Empty configuration renders a setup screen; these fallbacks never receive requests.
export const supabase = createClient(config.supabaseUrl || 'https://unconfigured.invalid', config.supabaseKey || 'unconfigured', {
  auth: {
    storage: Platform.OS === 'web' ? browserStorage : nativeStorage,
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: false,
    flowType: 'pkce',
  },
});
