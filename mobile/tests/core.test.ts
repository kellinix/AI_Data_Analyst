import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ApiError, createApi, errorDetail } from '../src/lib/api-core';
import { chunkedStorage, type KeyValueStore } from '../src/lib/secure-storage';
import { chartDocument } from '../src/lib/chart-document';
import { formatMetric } from '../src/lib/format';
import type { Insight } from '../src/generated/contracts';

function memoryStore() {
  const values = new Map<string, string>();
  const store: KeyValueStore = {
    async getItem(key) { return values.get(key) ?? null; },
    async setItem(key, value) { values.set(key, value); },
    async removeItem(key) { values.delete(key); },
  };
  return { values, store };
}

test('large Unicode auth sessions round-trip in bounded encrypted pieces', async () => {
  const { values, store } = memoryStore();
  const storage = chunkedStorage(store);
  const session = JSON.stringify({ token: 'x'.repeat(12_000), name: '😀'.repeat(1000) });
  await storage.setItem('auth', session);
  assert.equal(await storage.getItem('auth'), session);
  for (const [key, value] of values) {
    if (!key.endsWith('.manifest')) assert.ok(Buffer.byteLength(value, 'utf8') <= 1600);
  }
  await storage.removeItem('auth');
  assert.equal(await storage.getItem('auth'), null);
  assert.equal(values.size, 0);
});

test('a failed encrypted-session update preserves the complete previous session', async () => {
  const { values, store } = memoryStore();
  const storage = chunkedStorage(store);
  await storage.setItem('auth', 'old session');
  const oldSize = values.size;
  const write = store.setItem;
  let attempts = 0;
  store.setItem = async (key, value) => {
    if (++attempts === 2) throw new Error('Keychain full');
    await write(key, value);
  };
  await assert.rejects(storage.setItem('auth', 'n'.repeat(1000)), /Keychain full/);
  assert.equal(await storage.getItem('auth'), 'old session');
  assert.equal(values.size, oldSize);
});

test('incomplete saved sessions never return a partial token', async () => {
  const { values, store } = memoryStore();
  const storage = chunkedStorage(store);
  await storage.setItem('auth', 'x'.repeat(600));
  const chunk = [...values.keys()].find((key) => !key.endsWith('.manifest'))!;
  values.delete(chunk);
  await assert.rejects(storage.getItem('auth'), /incomplete/);
});

test('concurrent refresh and session reads cannot race chunk cleanup', async () => {
  const { store, values } = memoryStore();
  const storage = chunkedStorage(store);
  await storage.setItem('auth', 'initial');
  const first = 'a'.repeat(2000), second = 'b'.repeat(2400);
  const operations = await Promise.all([
    storage.setItem('auth', first), storage.getItem('auth'),
    storage.setItem('auth', second), storage.getItem('auth'),
  ]);
  assert.equal(operations[1], first);
  assert.equal(operations[3], second);
  assert.equal(values.size, 7); // six pieces and one manifest
});

test('requests use a fresh access token and the existing API prefix', async () => {
  let seenUrl = '';
  let headers: HeadersInit | undefined;
  let body: BodyInit | null | undefined;
  const api = createApi('https://api.example.test', async () => 'fresh-token', async (url, init) => {
    seenUrl = String(url); headers = init?.headers; body = init?.body;
    return Response.json({ id: 'analysis' });
  });
  assert.deepEqual(await api('/analyses', { method: 'POST', body: { file_id: 'file' } }), { id: 'analysis' });
  assert.equal(seenUrl, 'https://api.example.test/api/v1/analyses');
  assert.equal(new Headers(headers).get('Authorization'), 'Bearer fresh-token');
  assert.equal(body, '{"file_id":"file"}');
});

test('missing sessions never send an API request', async () => {
  let calls = 0;
  const api = createApi('https://api.example.test', async () => null, async () => { calls++; return Response.json({}); });
  await assert.rejects(api('/users/me'), (error) => error instanceof ApiError && error.status === 401);
  assert.equal(calls, 0);
});

test('delete endpoints accept the backend’s empty 204 response', async () => {
  const api = createApi('https://api.example.test', async () => 'token', async () => new Response(null, { status: 204 }));
  assert.equal(await api('/users/me', { method: 'DELETE' }), undefined);
});

test('backend validation and quota messages reach the user', async () => {
  assert.equal(errorDetail({ detail: [{ msg: 'Field is required' }] }, 'fallback'), 'Field is required');
  const api = createApi('https://api.example.test', async () => 'token', async () => Response.json({ detail: 'Monthly limit reached' }, { status: 402 }));
  await assert.rejects(api('/analyses'), (error) => error instanceof ApiError && error.message === 'Monthly limit reached' && error.status === 402);
});

test('timeouts abort the network request and return a retryable explanation', async () => {
  let aborted = false;
  const api = createApi('https://api.example.test', async () => 'token', async (_url, init) => new Promise((_resolve, reject) => {
    init?.signal?.addEventListener('abort', () => { aborted = true; reject(new Error('aborted')); });
  }));
  await assert.rejects(api('/analyses', { timeout: 10 }), /timed out/);
  assert.equal(aborted, true);
});

test('chart text cannot escape the serialized script into executable HTML', () => {
  const attack = '</script><script>window.stolen=true</script>';
  const html = chartDocument('/* local chart runtime */', { series: [{ data: [{ name: attack, value: 1 }] }] });
  assert.ok(!html.includes(attack));
  assert.ok(html.includes('\\u003c/script>'));
  assert.ok(html.includes("connect-src 'none'"));
  assert.ok(!html.includes('eval('));
});

test('metric formatting preserves percentages, negative values, and unknown currency', () => {
  const metric = (data: Record<string, unknown>) => ({ data } as Insight);
  assert.ok(formatMetric(metric({ value: 12.5, is_percent: true })).endsWith('%'));
  assert.ok(formatMetric(metric({ value: -1000 })).startsWith('-'));
  assert.ok(formatMetric(metric({ value: 1500, is_currency: true, currency: 'GBP' })).includes('£'));
  assert.ok(!formatMetric(metric({ value: 1500, is_currency: true })).includes('$'));
  assert.equal(formatMetric(metric({ value: NaN })), '—');
});
