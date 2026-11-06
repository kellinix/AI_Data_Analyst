import assert from 'node:assert/strict';
import { test } from 'node:test';
import { Buffer } from 'node:buffer';
import { verifyReleaseAuth } from '../scripts/verify-release-auth.mjs';

const url = 'https://project.supabase.co';
const publicKey = 'sb_publishable_test_value';
const configuration = { EXPO_PUBLIC_SUPABASE_URL: url, EXPO_PUBLIC_SUPABASE_ANON_KEY: publicKey };
const legacy = claims => `eyJhbGciOiJIUzI1NiJ9.${Buffer.from(JSON.stringify(claims)).toString('base64url')}.test_signature`;

test('a store build checks its public key against the configured Auth endpoint', async () => {
  let calls = 0;
  const result = await verifyReleaseAuth(configuration, async (endpoint, options) => {
    calls++;
    assert.equal(endpoint, `${url}/auth/v1/settings`);
    assert.deepEqual(options.headers, { apikey: publicKey });
    return { ok: true, status: 200 };
  });
  assert.equal(calls, 1);
  assert.equal(result.status, 200);
});

test('a revoked or incorrect public key blocks a store build without disclosing the key', async () => {
  await assert.rejects(verifyReleaseAuth(configuration, async () => ({ ok: false, status: 401 })), error => {
    assert.match(error.message, /rejected.*HTTP 401/);
    assert.ok(!error.message.includes(publicKey));
    return true;
  });
});

test('wrong-project and privileged keys are rejected before any network request', async () => {
  const neverRequest = () => { assert.fail('An unsafe key must not be transmitted.'); };
  for (const key of [
    'sb_secret_test_value',
    legacy({ role: 'service_role', ref: 'project', exp: 4_000_000_000 }),
    legacy({ role: 'anon', ref: 'different', exp: 4_000_000_000 }),
  ]) {
    await assert.rejects(verifyReleaseAuth({ ...configuration, EXPO_PUBLIC_SUPABASE_ANON_KEY: key }, neverRequest));
  }
});

test('an accepted legacy anon key remains supported', async () => {
  const key = legacy({ role: 'anon', ref: 'project', exp: 4_000_000_000 });
  const result = await verifyReleaseAuth({ ...configuration, EXPO_PUBLIC_SUPABASE_ANON_KEY: key }, async () => ({ ok: true, status: 200 }));
  assert.equal(result.status, 200);
});

test('missing configuration, expired keys and insecure origins block release validation', async () => {
  const neverRequest = () => { assert.fail('Invalid configuration must not be transmitted.'); };
  for (const env of [
    {}, { ...configuration, EXPO_PUBLIC_SUPABASE_URL: 'http://project.supabase.co' },
    { ...configuration, EXPO_PUBLIC_SUPABASE_ANON_KEY: legacy({ role: 'anon', ref: 'project', exp: 1 }) },
  ]) await assert.rejects(verifyReleaseAuth(env, neverRequest));
});

test('network failures cannot leak request credentials into build errors', async () => {
  await assert.rejects(verifyReleaseAuth(configuration, async () => { throw new Error(publicKey); }), error => {
    assert.match(error.message, /Could not verify/);
    assert.ok(!error.message.includes(publicKey));
    return true;
  });
});
