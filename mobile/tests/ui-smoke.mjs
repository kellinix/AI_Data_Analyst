import assert from 'node:assert/strict';
import { Buffer } from 'node:buffer';
import { createRequire } from 'node:module';
import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

// Uses the repository's existing Playwright installation. All auth/API traffic
// is intercepted: this test cannot upload data or delete a real account.
const root = fileURLToPath(new URL('../', import.meta.url));
const require = createRequire(path.join(root, '../frontend/package.json'));
const { chromium } = require('@playwright/test');
const userId = '11111111-1111-4111-8111-111111111111';
const analysisId = '22222222-2222-4222-8222-222222222222';
const sessionId = '33333333-3333-4333-8333-333333333333';
const timestamp = '2026-10-07T09:00:00Z';
const user = { id: userId, aud: 'authenticated', email: 'mobile@example.test', user_metadata: { full_name: 'Mobile Tester' }, app_metadata: {}, created_at: timestamp };
const profile = { ...user, full_name: 'Mobile Tester', plan: 'free', subscription: null, usage: { analyses_this_month: 1, analyses_limit: 5, storage_used_bytes: 1500, storage_limit_bytes: 104857600, ai_queries_this_month: 0, ai_queries_limit: 20 } };
const baseInsight = { analysis_id: analysisId, importance: 'high', confidence: 0.8, created_at: timestamp, chart_config: null };
const analysis = {
  id: analysisId, name: 'Regional sales', status: 'completed', file_id: 'test-file', filename: 'sales.csv', row_count: 936, column_count: 5, created_at: timestamp, updated_at: timestamp,
  summary: 'Revenue rose steadily across the period. The North region contributed the largest share.',
  insights: [{ ...baseInsight, id: 'kpi', type: 'summary', title: 'Revenue', description: 'Total revenue in GBP', data: { value: 150000, is_currency: true, currency: 'GBP' } }, { ...baseInsight, id: 'recommendation', type: 'recommendation', title: 'Review regional performance', description: 'Compare the North region with the other regions.', data: {}, user_feedback: null }],
  charts: [{ id: 'sales-chart', type: 'bar', title: 'Revenue by region', description: 'Total revenue for each region.', currency: 'GBP', echarts_option: { grid: { left: 60, right: 15, bottom: 35, top: 15 }, xAxis: { type: 'category', data: ['North', 'South', 'West'] }, yAxis: { type: 'value' }, series: [{ type: 'bar', data: [70000, 45000, 35000], itemStyle: { color: '#265DF2' } }] } }],
  filterable_columns: [], metadata: {
    data_quality: { score: 98, issues: [], scope: 'Checks on analysis records; real-world accuracy is not verified.', empty_fields: ['Actual Project Duration'], scoring_method: 'Empty fields are reported separately.',
      source_quality: { score: 81, scope: 'Source completeness only; missing fields may be optional.', issues: [{ column: 'region', description: '10 source values are missing' }] } },
    analysis_evidence: { entity_counts: [{ column: 'customer_id', distinct_values: 400, count_basis: 'Distinct recorded values; real-world identity is not verified.' }],
      limitations: ['Counts describe records unless a distinct-value measure is explicitly stated.'],
      cleaning: { input_rows: 940, output_rows: 936, reconciled: true, row_changes: [{ reason: 'Exact duplicates removed after normalization', rows: 4 }] } },
  },
};
const messages = [];
let uploadCalls = 0;
let analysisCalls = 0;
let chatCalls = 0;
let feedbackCalls = 0;
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, acceptDownloads: true });
const page = await context.newPage();
const errors = [];
page.on('pageerror', (error) => errors.push(error.message));
await page.route('https://mobile-fixture.invalid/**', async (route) => {
  const request = route.request();
  let body = { ...user };
  if (request.url().includes('/token')) {
    const payload = JSON.parse(request.postData() ?? '{}');
    assert.equal(payload.email, 'mobile@example.test');
    const jwt = ['header', Buffer.from(JSON.stringify({ sub: userId, exp: Math.floor(Date.now() / 1000) + 3600 })).toString('base64url'), 'signature'].join('.');
    body = { access_token: jwt, refresh_token: 'fixture-refresh', token_type: 'bearer', expires_in: 3600, user };
  }
  await route.fulfill({ json: body, headers: { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*' } });
});
await page.route('http://127.0.0.1:8000/api/v1/**', async (route) => {
  const request = route.request();
  const url = new URL(request.url());
  const method = request.method();
  const pathname = url.pathname.replace('/api/v1', '');
  const headers = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS' };
  if (method === 'OPTIONS') return route.fulfill({ status: 204, headers });
  assert.ok(request.headers().authorization?.startsWith('Bearer '));
  let body;
  if (pathname === '/users/me') body = profile;
  else if (pathname === '/uploads') {
    assert.ok(request.headers()['content-type'].includes('multipart/form-data'));
    uploadCalls++;
    body = { id: 'test-file', original_filename: 'sales.csv', row_count: 2, column_count: 2 };
  } else if (pathname === '/analyses' && method === 'POST') { analysisCalls++; body = analysis; }
  else if (pathname === '/analyses') body = { items: [analysis], total: 1, page: 1, pages: 1, limit: 20 };
  else if (pathname === `/analyses/${analysisId}`) body = analysis;
  else if (pathname.endsWith('/feedback')) { feedbackCalls++; analysis.insights[1].user_feedback = 'helpful'; body = { verdict: 'helpful' }; }
  else if (pathname.endsWith('/export/pdf')) return route.fulfill({ body: '%PDF-1.4\nfixture report', contentType: 'application/pdf', headers });
  else if (pathname === '/chat/sessions') body = method === 'POST' ? { id: sessionId } : [];
  else if (pathname.endsWith('/messages')) {
    if (method === 'POST') {
      chatCalls++;
      const content = JSON.parse(request.postData()).content;
      messages.push({ id: 'message-user', session_id: sessionId, role: 'user', content, created_at: timestamp }, { id: 'message-ai', session_id: sessionId, role: 'assistant', content: 'The North region generated the most revenue.', created_at: timestamp });
      body = messages.at(-1);
    } else body = messages;
  } else throw new Error(`Unexpected API request: ${method} ${pathname}`);
  await route.fulfill({ json: body, headers });
});

try {
  await mkdir(path.join(root, 'artifacts'), { recursive: true });
  await page.goto('http://localhost:8082', { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Sign in', exact: true }).waitFor({ timeout: 120_000 });
  await page.getByRole('button', { name: 'Continue with Google' }).waitFor();
  await page.screenshot({ path: path.join(root, 'artifacts/sign-in.png'), fullPage: true });
  await page.getByRole('textbox', { name: 'Email', exact: true }).fill('mobile@example.test');
  await page.getByLabel('Password', { exact: true }).fill('test-password-only');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await page.getByRole('button', { name: 'Open Regional sales' }).waitFor();
  await page.screenshot({ path: path.join(root, 'artifacts/analyses.png'), fullPage: true });
  await page.getByRole('button', { name: 'Open Regional sales' }).click();
  await page.getByText('Executive summary', { exact: true }).waitFor();
  await page.getByText('What these results cover', { exact: true }).waitFor();
  await page.getByText('Source completeness', { exact: true }).waitFor();
  await page.getByText('Empty fields are reported separately.', { exact: true }).waitFor();
  await page.getByText('Fields with no supplied values: Actual Project Duration. Confirm which are required.', { exact: true }).waitFor();
  await page.getByText('region: 10 source values are missing', { exact: true }).waitFor();
  const frame = page.frameLocator('iframe[title="Revenue by region"]');
  await frame.locator('canvas').waitFor();
  assert.equal(await frame.locator('#chart').evaluate((node) => node.textContent.includes('could not')), false);
  await page.screenshot({ path: path.join(root, 'artifacts/dashboard.png'), fullPage: true });
  await page.getByRole('button', { name: 'Helpful', exact: true }).click();
  await page.getByRole('button', { name: 'Helpful ✓', exact: true }).waitFor();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export PDF', exact: true }).click();
  assert.ok((await download).suggestedFilename().endsWith('.pdf'));
  await page.getByRole('button', { name: 'Ask a question about this data' }).click();
  await page.getByRole('button', { name: 'Summarise the key findings', exact: true }).waitFor();
  await page.getByRole('button', { name: 'Summarise the key findings', exact: true }).click();
  await page.getByText('The North region generated the most revenue.', { exact: true }).waitFor();
  await page.screenshot({ path: path.join(root, 'artifacts/chat.png'), fullPage: true });
  await page.goto('http://localhost:8082/upload');
  await page.getByRole('button', { name: 'Browse files' }).waitFor();
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Browse files' }).click();
  await (await chooser).setFiles({ name: 'sales.csv', mimeType: 'text/csv', buffer: Buffer.from('region,revenue\nNorth,100\nSouth,50\n') });
  await page.getByText('sales.csv', { exact: true }).waitFor();
  await page.getByRole('button', { name: 'Create analysis', exact: true }).click();
  await page.getByText('Executive summary', { exact: true }).waitFor();
  assert.equal(uploadCalls, 1); assert.equal(analysisCalls, 1); assert.equal(chatCalls, 1); assert.equal(feedbackCalls, 1);
  await page.goto('http://localhost:8082/settings');
  await page.getByRole('textbox', { name: 'Full name', exact: true }).waitFor();
  await page.screenshot({ path: path.join(root, 'artifacts/settings.png'), fullPage: true });
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await page.getByRole('button', { name: 'Sign in', exact: true }).waitFor();
  await page.goto(`http://localhost:8082/analysis/${analysisId}`);
  await page.getByRole('button', { name: 'Sign in', exact: true }).waitFor();
  assert.deepEqual(errors, []);
  console.log('Mobile web smoke passed: sign-in, protected routes, dashboard chart, feedback, export, chat, upload, settings, sign-out.');
} finally { await browser.close(); }
