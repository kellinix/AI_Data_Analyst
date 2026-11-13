import assert from 'node:assert/strict';
import { test } from 'node:test';
import { randomFillSync, webcrypto } from 'node:crypto';
import { runInNewContext } from 'node:vm';
import { createClient } from '@supabase/supabase-js';
import { ApiError, createApi, errorDetail } from '../src/lib/api-core';
import { chunkedStorage, type KeyValueStore } from '../src/lib/secure-storage';
import { chartDocument, chartDocumentHeight } from '../src/lib/chart-document';
import { analysisSourceLabel, formatMetric } from '../src/lib/format';
import { installPkceCrypto } from '../src/lib/pkce-crypto';
import type { Insight } from '../src/generated/contracts';
import { performAppleSignIn } from '../src/lib/apple-sign-in';
import { requireAiConsent } from '../src/lib/ai-consent';

test('Apple sign-in sends a hashed nonce to Apple and the raw nonce only to verification', async () => {
  const values = ['private-nonce', 'request-state'];
  const calls: unknown[] = [];
  await performAppleSignIn({
    random: () => values.shift()!,
    sha256: async value => `hash(${value})`,
    authorize: async (nonce, state) => { calls.push({ nonce, state }); return { identityToken: 'signed-token', state }; },
    exchange: async (token, nonce) => { calls.push({ token, nonce }); return { error: null }; },
  });
  assert.deepEqual(calls, [{ nonce: 'hash(private-nonce)', state: 'request-state' }, { token: 'signed-token', nonce: 'private-nonce' }]);
});

test('Apple sign-in rejects missing tokens and mismatched state without exchanging them', async () => {
  for (const credential of [{ identityToken: null, state: 'random' }, { identityToken: 'token', state: 'wrong-state' }]) {
    let exchanges = 0;
    await assert.rejects(performAppleSignIn({ random: () => 'random', sha256: async () => 'hash', authorize: async () => credential, exchange: async () => { exchanges++; return { error: null }; } }));
    assert.equal(exchanges, 0);
  }
});

test('Apple sign-in propagates rejected server verification', async () => {
  await assert.rejects(performAppleSignIn({ random: () => 'random', sha256: async () => 'hash', authorize: async () => ({ identityToken: 'token', state: 'random' }), exchange: async () => ({ error: new Error('Rejected token') }) }), /Rejected token/);
});

test('AI requests require an affirmative consent choice', () => {
  assert.throws(() => requireAiConsent(false), /share data with OpenAI/);
  assert.doesNotThrow(() => requireAiConsent(true));
});

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

function renderedChartOption(option: Record<string, unknown>, currency?: string, legendText?: string[]) {
  let captured: Record<string, unknown> = {};
  const html = chartDocument('/* test runtime */', option, currency);
  const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
  const element = () => ({ style: {}, textContent: '', setAttribute: () => {},
    appendChild: (child: { textContent: string }) => { if (child.textContent) legendText?.push(child.textContent); } });
  runInNewContext(scripts[scripts.length - 1][1], {
    document: { getElementById: element, createElement: element, body: element() },
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
  const xAxis = option.xAxis as { nameLocation: string; nameGap: number };
  assert.equal(xAxis.nameLocation, 'middle');
  assert.equal(xAxis.nameGap, 38);
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

test('native lines retain all three complete recorded series and their legend', () => {
  const names = ['Average G', 'Average AB', 'Average R'];
  const option = renderedChartOption({
    legend: { show: true, bottom: 0 },
    xAxis: { type: 'category', data: Array.from({ length: 938 }, (_, index) => String(index)) },
    yAxis: { type: 'value' },
    series: names.map((name, metric) => ({ type: 'line', name,
      data: Array.from({ length: 938 }, (_, index) => index + metric) })),
  });
  const series = option.series as { name: string; data: number[] }[];
  assert.deepEqual(Array.from(series, item => item.name), names);
  assert.deepEqual(Array.from(series, item => item.data.length), [938, 938, 938]);
  assert.equal(series[2].data[937], 939);
  assert.equal((option.legend as { show: boolean }).show, true);
});

test('guide meanings change native labels and tooltips while preserving raw categories', () => {
  const option = renderedChartOption({ _group_counts: { M: 3 },
    _reader_value_maps: { yAxis: { field: 'status', values: [{ value: 'M', label: 'Married' }] } },
    xAxis: { type: 'value' }, yAxis: { type: 'category', data: ['M', 'S'] },
    series: [{ type: 'bar', name: 'Amount', data: [10, 20] }],
  });
  const axis = option.yAxis as { data: string[]; axisLabel: { formatter: (value: string) => string } };
  assert.deepEqual(Array.from(axis.data), ['M', 'S']);
  assert.equal(axis.axisLabel.formatter('M'), 'Married (M)');
  assert.equal(axis.axisLabel.formatter('S'), 'S');
  const tooltip = option.tooltip as { formatter: (items: { name: string; seriesName: string; value: number }[]) => string };
  const text = tooltip.formatter([{ name: 'M', seriesName: 'Amount', value: 10 }]);
  assert.ok(text.includes('Married (M)') && text.includes('3 entries with a supplied value'));
});

test('guide meanings label native pie legends and split series without changing names', () => {
  const pie = renderedChartOption({ _reader_value_maps: { pie: { field: 'status', values: [{ value: 'M', label: 'Married' }] } },
    series: [{ type: 'pie', data: [{ name: 'M', value: 2 }] }],
  });
  const media = pie.media as { option: { legend: { formatter: (name: string) => string } } }[];
  assert.ok(media[0].option.legend.formatter('M').startsWith('Married (M)\n2'));
  assert.equal((pie.series as { data: { name: string }[] }[])[0].data[0].name, 'M');
  const grouped = renderedChartOption({ _reader_value_maps: { series: { field: 'status', values: [{ value: 'M', label: 'Married' }] } },
    xAxis: { type: 'category', data: ['A'] }, yAxis: { type: 'value' },
    series: [{ type: 'bar', name: 'M', data: [2] }],
  });
  assert.equal((grouped.legend as { formatter: (name: string) => string }).formatter('M'), 'Married (M)');
  assert.equal((grouped.series as { name: string }[])[0].name, 'M');
});

test('native guide lookup treats reserved-property codes as plain labels', () => {
  const option = renderedChartOption({ _reader_value_maps: {
    pie: { field: 'code', values: [{ value: '__proto__', label: 'Special code' }] },
  }, series: [{ type: 'pie', data: [{ name: '__proto__', value: 2 }, { name: 'constructor', value: 1 }] }] });
  const media = option.media as { option: { legend: { formatter: (name: string) => string } } }[];
  assert.ok(media[0].option.legend.formatter('__proto__').startsWith('Special code (__proto__)'));
  assert.ok(media[0].option.legend.formatter('constructor').startsWith('constructor\n1'));
});

test('an empty pie code keeps its meaning and all figures in a visible native legend', () => {
  const input = { _reader_value_maps: { pie: { field: 'codeshare', values: [
    { value: '', label: 'Other route' }, { value: 'Y', label: 'Operated by another carrier' },
  ] } }, series: [{ type: 'pie', data: [{ name: '', value: 53066 }, { name: 'Y', value: 14597 }] }] };
  const text: string[] = [];
  const option = renderedChartOption(input, undefined, text);
  assert.ok(text.some(value => value.includes('Other route ("")\n53,066 (78.4%)')));
  assert.ok(text.some(value => value.includes('Operated by another carrier (Y)\n14,597 (21.6%)')));
  assert.equal((option.legend as { show: boolean }).show, false);
  const points = (option.series as { data: { name: string; value: number }[] }[])[0].data;
  assert.deepEqual(Array.from(points, point => [point.name, point.value]), [['', 53066], ['Y', 14597]]);
  assert.ok(chartDocumentHeight(input) > 320);
  assert.equal(chartDocumentHeight({ series: [{ type: 'pie', data: [{ name: 'Y', value: 2 }] }] }), 320);
  const long = structuredClone(input);
  long._reader_value_maps.pie.values[0].label = 'A'.repeat(80);
  assert.ok(chartDocumentHeight(long) > chartDocumentHeight(input));
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

test('analysis headers use recorded source names and hide internal parquet identifiers', () => {
  const internal = '8c36c90f-78cc-448b-b9cb-f4d9ee242560.cleaned.parquet';
  assert.equal(analysisSourceLabel({ filename: internal, metadata: { upload_context: {
    cleaning: { source_filename: 'inventory.csv' },
  } } }), 'inventory.csv');
  assert.equal(analysisSourceLabel({ filename: internal, metadata: { upload_context: {
    source_files: [{ name: 'inventory.csv' }, { name: 'products.csv' }, { name: 'stores.csv' }],
  } } }), 'inventory.csv, products.csv, stores.csv');
  assert.equal(analysisSourceLabel({ filename: 'Sales 2025.csv', metadata: {} }), 'Sales 2025.csv');
  assert.equal(analysisSourceLabel({ filename: internal, metadata: {} }), null);
  assert.equal(analysisSourceLabel({ filename: 'a'.repeat(32) + '.parquet', metadata: {} }), null);
  assert.equal(analysisSourceLabel({ filename: internal, metadata: { upload_context: {
    files: [{ name: 'C:\\private\\inventory.csv' }],
  } } }), 'inventory.csv');
});
