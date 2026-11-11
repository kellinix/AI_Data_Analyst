import assert from 'node:assert/strict';
import { test } from 'node:test';
import { randomFillSync, webcrypto } from 'node:crypto';
import { runInNewContext } from 'node:vm';
import { createClient } from '@supabase/supabase-js';
import { ApiError, createApi, errorDetail } from '../src/lib/api-core';
import { chunkedStorage, type KeyValueStore } from '../src/lib/secure-storage';
import { chartDocument } from '../src/lib/chart-document';
import { formatMetric } from '../src/lib/format';
import { installPkceCrypto } from '../src/lib/pkce-crypto';
import type { Insight } from '../src/generated/contracts';

test('native PKCE uses secure randomness and an S256 challenge', async () => {
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'crypto');
  Object.defineProperty(globalThis, 'crypto', { configurable: true, writable: true, value: undefined });
  let randomCalls = 0;
  let digestCalls = 0;
  try {
    installPkceCrypto(globalThis, {
      getRandomValues: (array) => { randomCalls++; return randomFillSync(array); },
      sha256: async (data) => { digestCalls++; return webcrypto.subtle.digest('SHA-256', data as never); },
    });
    const { store } = memoryStore();
    const client = createClient('https://example.supabase.co', 'test-public-key', {
      auth: { storage: store, flowType: 'pkce', autoRefreshToken: false, persistSession: true },
    });
    const result = await client.auth.signInWithOAuth({ provider: 'google', options: { skipBrowserRedirect: true } });
    assert.equal(result.error, null);
    assert.ok(result.data.url);
    const url = new URL(result.data.url);
    assert.equal(url.searchParams.get('code_challenge_method'), 's256');
    assert.match(url.searchParams.get('code_challenge') ?? '', /^[A-Za-z0-9_-]{43}$/);
    assert.ok(randomCalls > 0);
    assert.ok(digestCalls > 0);
  } finally {
    if (previous) Object.defineProperty(globalThis, 'crypto', previous);
    else Reflect.deleteProperty(globalThis, 'crypto');
  }
});

test('PKCE crypto does not replace native random failures with a weak fallback', () => {
  const target: { crypto?: unknown } = {};
  installPkceCrypto(target, {
    getRandomValues: () => { throw new Error('Native secure random unavailable'); },
    sha256: async () => new ArrayBuffer(32),
  });
  const crypto = target.crypto as { getRandomValues: (input: Uint32Array) => Uint32Array };
  assert.throws(() => crypto.getRandomValues(new Uint32Array(56)), /Native secure random unavailable/);
});

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

function renderedChartOption(option: Record<string, unknown>, currency?: string) {
  let captured: Record<string, unknown> = {};
  const html = chartDocument('/* test runtime */', option, currency);
  const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
  runInNewContext(scripts[scripts.length - 1][1], {
    document: { getElementById: () => ({ textContent: '' }) },
    echarts: { init: () => ({ setOption: (value: Record<string, unknown>) => { captured = value; }, resize: () => {} }) },
    window: { addEventListener: () => {} },
    Intl,
  });
  return captured;
}

test('narrow bar charts wrap full names and keep exact figures and counts in the tooltip', () => {
  const name = 'PlayDoh Kitchen Creations';
  const option = renderedChartOption({ _group_counts: { [name]: 50 },
    xAxis: { type: 'value' }, yAxis: { type: 'category', data: [name] },
    series: [{ type: 'bar', name: 'Total stock on hand', data: [2738] }],
  });
  const media = option.media as { option: { grid: { right: number }; yAxis: { axisLabel: { width: number; overflow: string } };
    series: { data: number[]; label: { formatter: (item: { value: number }) => string } }[] } }[];
  const narrow = media[0].option;
  assert.equal(narrow.yAxis.axisLabel.overflow, 'break');
  assert.equal(narrow.yAxis.axisLabel.width, 112);
  assert.equal(narrow.grid.right, 56);
  assert.deepEqual(Array.from(narrow.series[0].data), [2738]);
  assert.ok(!narrow.series[0].label.formatter({ value: 2738 }).includes('records'));
  const tooltip = option.tooltip as { formatter: (items: { name: string; value: number; seriesName: string }[]) => string };
  const text = tooltip.formatter([{ name, value: 2738, seriesName: 'Total stock on hand' }]);
  assert.ok(text.includes(name) && text.includes('50 entries with a supplied value'));
});

test('narrow pie charts retain full category names and exact values in an informational legend', () => {
  const option = renderedChartOption({ series: [{ type: 'pie', data: [
    { name: 'Sports & Outdoors', value: 323 }, { name: 'Art & Crafts', value: 397 },
  ] }] });
  const media = option.media as { option: { legend: { selectedMode: boolean; formatter: (name: string) => string };
    series: { label: { show: boolean }; data: { name: string; value: number }[] }[] } }[];
  const narrow = media[0].option;
  assert.equal(narrow.legend.selectedMode, false);
  assert.equal(narrow.series[0].label.show, false);
  assert.ok(narrow.legend.formatter('Sports & Outdoors').includes('Sports & Outdoors\n323'));
  assert.equal(narrow.series[0].data[1].value, 397);
});

test('a money scatter chart keeps quantity and money axis units separate', () => {
  const option = renderedChartOption({ xAxis: { type: 'value', _currency: null },
    yAxis: { type: 'value', _currency: 'GBP' }, series: [{ type: 'scatter', data: [[2, 3]] }] }, 'GBP');
  const xAxis = option.xAxis as { axisLabel: { formatter: (value: number) => string } };
  const yAxis = option.yAxis as { axisLabel: { formatter: (value: number) => string } };
  assert.ok(!xAxis.axisLabel.formatter(2).includes('£'));
  assert.ok(yAxis.axisLabel.formatter(3).includes('£'));
});

test('metric formatting preserves percentages, negative values, and unknown currency', () => {
  const metric = (data: Record<string, unknown>) => ({ data } as Insight);
  assert.ok(formatMetric(metric({ value: 12.5, is_percent: true })).endsWith('%'));
  assert.ok(formatMetric(metric({ value: -1000 })).startsWith('-'));
  assert.ok(formatMetric(metric({ value: 1500, is_currency: true, currency: 'GBP' })).includes('£'));
  assert.match(formatMetric(metric({ value: 7310.95, is_currency: true, currency: 'GBP', unit: 'million' })), /million$/);
  assert.ok(!formatMetric(metric({ value: 1500, is_currency: true })).includes('$'));
  assert.equal(formatMetric(metric({ value: NaN })), '—');
});
