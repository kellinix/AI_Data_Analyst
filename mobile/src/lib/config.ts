import { Platform } from 'react-native';

const nativeApiUrl = process.env.EXPO_PUBLIC_API_URL?.trim().replace(/\/+$/, '') ?? '';
const webApiUrl = process.env.EXPO_PUBLIC_WEB_API_URL?.trim().replace(/\/+$/, '') ?? '';
const apiUrl = Platform.OS === 'web' && webApiUrl ? webApiUrl : nativeApiUrl;
const supabaseUrl = process.env.EXPO_PUBLIC_SUPABASE_URL?.trim().replace(/\/+$/, '') ?? '';
const supabaseKey = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY?.trim() ?? '';

export const config = { apiUrl, supabaseUrl, supabaseKey };
export const configurationErrors = [
  ...(!apiUrl ? ['EXPO_PUBLIC_API_URL'] : []),
  ...(!supabaseUrl ? ['EXPO_PUBLIC_SUPABASE_URL'] : []),
  ...(!supabaseKey ? ['EXPO_PUBLIC_SUPABASE_ANON_KEY'] : []),
];
for (const [label, value] of [['API', apiUrl], ['Supabase', supabaseUrl]]) {
  if (!value) continue;
  try {
    const url = new URL(value);
    if (!['http:', 'https:'].includes(url.protocol)) throw new Error();
    if (!__DEV__ && url.protocol !== 'https:') configurationErrors.push(`${label} must use HTTPS for release builds`);
  } catch {
    configurationErrors.push(`${label} URL is invalid`);
  }
}
export const isConfigured = configurationErrors.length === 0;
