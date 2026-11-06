import { pathToFileURL } from 'node:url';
import { Buffer } from 'node:buffer';

export async function verifyReleaseAuth(env, request = fetch) {
  const rawUrl = env.EXPO_PUBLIC_SUPABASE_URL?.trim();
  const key = env.EXPO_PUBLIC_SUPABASE_ANON_KEY?.trim();
  if (!rawUrl || !key) throw new Error('Release authentication requires a Supabase URL and public key.');
  let url;
  try { url = new URL(rawUrl); } catch { throw new Error('Release Supabase URL is invalid.'); }
  if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash || url.pathname !== '/') {
    throw new Error('Release Supabase URL must be an HTTPS project origin.');
  }
  if (!/^sb_publishable_[A-Za-z0-9_-]+$/.test(key)) {
    let claims;
    try {
      if (!/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(key)) throw new Error();
      claims = JSON.parse(Buffer.from(key.split('.')[1], 'base64url').toString('utf8'));
    } catch {
      throw new Error('Release Supabase key must be a publishable key or legacy anon key.');
    }
    if (claims.role !== 'anon') throw new Error('Privileged Supabase keys cannot be shipped in a mobile app.');
    if (url.hostname.endsWith('.supabase.co') && claims.ref !== url.hostname.split('.')[0]) {
      throw new Error('Release Supabase URL and anon key belong to different projects.');
    }
    if (typeof claims.exp !== 'number' || claims.exp <= Date.now() / 1000) {
      throw new Error('Release Supabase anon key is expired or has no expiry.');
    }
  }
  let response;
  try {
    response = await request(`${url.origin}/auth/v1/settings`, {
      headers: { apikey: key }, signal: AbortSignal.timeout(20_000),
    });
  } catch {
    // Provider/client errors may contain request headers; never echo them into build logs.
    throw new Error('Could not verify release Supabase authentication. Retry when the project is reachable.');
  }
  if (!response.ok) {
    throw new Error(`Release Supabase authentication rejected the public key (HTTP ${response.status}).`);
  }
  return { origin: url.origin, status: response.status };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const profile = process.env.EAS_BUILD_PROFILE;
  if (profile && !['production', 'store-test'].includes(profile)) {
    console.log('Skipping standalone release auth check for a development build.');
  } else {
    verifyReleaseAuth(process.env).then(() => {
      console.log('Release public Supabase key accepted by the configured Auth project.');
    }).catch(error => {
      console.error(error.message);
      process.exitCode = 1;
    });
  }
}
