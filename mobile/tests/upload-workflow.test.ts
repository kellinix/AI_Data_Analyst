import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import type { DocumentPickerAsset } from 'expo-document-picker';
import type { UploadedFile } from '../src/generated/contracts';
import { generateRelationshipSuggestions } from '../src/generated/upload-relationships';
import { parseDataGuide, readDataGuide } from '../src/generated/data-guide';
import { addUploadAssets, analysisUploadRequest, profileUploadQueue } from '../src/lib/upload-workflow';
import { createApi } from '../src/lib/api-core';

function asset(name: string, size = 20): DocumentPickerAsset {
  return { name, size, lastModified: 123, uri: `file:///test/${name}` };
}

function profile(name: string, columns: string[]): UploadedFile {
  return {
    id: name, original_filename: name, filename: name, user_id: 'test-user', file_size: 20,
    mime_type: 'text/csv', storage_path: '', row_count: 10, column_count: columns.length, created_at: '',
    columns: columns.map(column => ({ name: column, dtype: 'String', non_null_count: 10,
      null_count: 0, unique_count: 10, sample_values: [] })),
  };
}

test('mobile uses the canonical website relationship detector', async () => {
  const source = await readFile(new URL('../../frontend/src/lib/upload-relationships.ts', import.meta.url), 'utf8');
  const generated = await readFile(new URL('../src/generated/upload-relationships.ts', import.meta.url), 'utf8');
  assert.equal(generated, '// Generated from frontend/src/lib/upload-relationships.ts.\n' + source.replace('from "@/types"', 'from "./contracts"'));
  const guideSource = await readFile(new URL('../../frontend/src/lib/data-guide.ts', import.meta.url), 'utf8');
  const guideGenerated = await readFile(new URL('../src/generated/data-guide.ts', import.meta.url), 'utf8');
  assert.equal(guideGenerated, '// Generated from frontend/src/lib/data-guide.ts.\n' + guideSource);
});

test('the mobile build archive includes its canonical relationship source', async () => {
  const ignore = await readFile(new URL('../../.easignore', import.meta.url), 'utf8');
  const patterns = ignore.split(/\r?\n/);
  assert.ok(patterns.includes('!/frontend/src/lib'));
  assert.ok(patterns.includes('!/frontend/src/lib/upload-relationships.ts'));
  assert.ok(patterns.includes('!/frontend/src/lib/data-guide.ts'));
});

test('multiple selections append in order and deduplicate within and across selections', () => {
  const first = addUploadAssets([], [asset('donors.csv'), asset('donors.csv'), asset('gifts.csv')]);
  assert.equal(first.length, 2);
  const next = addUploadAssets(first, [asset('donors.csv'), asset('regions.xlsx')]);
  assert.deepEqual(next.map(item => item.asset.name), ['donors.csv', 'gifts.csv', 'regions.xlsx']);
  assert.equal(first.length, 2);
});

test('selection validates every file and the pending batch storage allowance atomically', () => {
  const queue = addUploadAssets([], [asset('donors.csv')], 100);
  assert.throws(() => addUploadAssets(queue, [asset('gifts.csv'), asset('bad.pdf')], 100), /Choose CSV/);
  assert.throws(() => addUploadAssets(queue, [asset('large.csv', 513 * 1024 * 1024)]), /512 MB/);
  assert.throws(() => addUploadAssets(queue, [asset('gifts.csv', 90)], 100), /remaining storage/);
  assert.equal(queue.length, 1);
  const uploaded = [{ ...queue[0], uploaded: profile('donors.csv', ['donor_id']) }];
  assert.equal(addUploadAssets(uploaded, [asset('gifts.csv', 90)], 100).length, 2);
  assert.equal(addUploadAssets([], [{ ...asset('unknown.csv'), size: undefined }], 0).length, 1);
});

test('a partial upload failure preserves successful files and a retry skips them', async () => {
  let queue = addUploadAssets([], [asset('donors.csv'), asset('gifts.csv'), asset('regions.csv')]);
  const uploadedNames: string[] = [];
  const progressIds: string[] = [];
  const save = (id: string, file: UploadedFile) => { queue = queue.map(item => item.id === id ? { ...item, uploaded: file } : item); };
  const progress = (id: string) => { progressIds.push(id); };
  await assert.rejects(profileUploadQueue(queue, async file => {
    uploadedNames.push(file.name);
    if (file.name === 'gifts.csv') throw new Error('Connection lost');
    return profile(file.name, ['donor_id']);
  }, progress, save), /Connection lost/);
  assert.equal(queue[0].uploaded?.id, 'donors.csv');
  assert.equal(queue[1].uploaded, undefined);
  await profileUploadQueue(queue, async (file, onProgress) => {
    uploadedNames.push(file.name);
    onProgress(50);
    return profile(file.name, ['donor_id']);
  }, progress, save);
  assert.deepEqual(uploadedNames, ['donors.csv', 'gifts.csv', 'gifts.csv', 'regions.csv']);
  assert.equal(queue.filter(item => item.uploaded).length, 3);
  assert.ok(progressIds.includes(queue[2].id));
});

test('related files, matching reports, workbook sheets and separate datasets receive suggestions', () => {
  const donors = profile('donors.csv', ['donor_id', 'segment', 'country']);
  const gifts = profile('gifts.csv', ['gift_id', 'donor_id', 'amount_usd', 'status']);
  const join = generateRelationshipSuggestions([donors, gifts]);
  assert.equal(join[0].type, 'join');
  assert.deepEqual(join[0].columns, ['donor_id']);
  const reports = generateRelationshipSuggestions([
    profile('sales-2024.csv', ['store_id', 'revenue']), profile('sales-2025.csv', ['store_id', 'revenue']),
  ]);
  assert.ok(reports.some(item => item.type === 'stack'));
  assert.ok(reports.some(item => item.type === 'compare'));
  assert.equal(generateRelationshipSuggestions([profile('book.xlsx', ['Sheet', 'revenue'])])[0].type, 'sheets');
  assert.equal(generateRelationshipSuggestions([donors, profile('weather.csv', ['temperature'])])[0].type, 'separate');
  assert.equal(generateRelationshipSuggestions([{ ...donors, columns: null }])[0].type, 'separate');
});

test('date and descriptive fields alone do not become record join keys', () => {
  const suggestions = generateRelationshipSuggestions([
    profile('sales.csv', ['date', 'description', 'revenue']),
    profile('support.csv', ['date', 'description', 'ticket_count']),
  ]);
  assert.ok(suggestions.every(item => item.type !== 'join'));
});

test('multiple uploads use the combined endpoint and include relationship evidence and user instructions', async () => {
  const files = [profile('donors.csv', ['donor_id', 'segment']), profile('gifts.csv', ['gift_id', 'donor_id', 'amount_usd'])];
  const request = analysisUploadRequest(files, ' Donor gifts ', ' Charitable donations ', ' Completed gifts only ', false);
  let seenUrl = '';
  let seenBody: unknown;
  const api = createApi('https://api.example.test', async () => 'token', async (url, init) => {
    seenUrl = String(url);
    seenBody = JSON.parse(String(init?.body));
    return Response.json({ id: 'combined-analysis' });
  });
  await api(request.path, { method: 'POST', body: request.body });
  assert.equal(seenUrl, 'https://api.example.test/api/v1/analyses/combined');
  assert.deepEqual(seenBody, request.body);
  assert.deepEqual('file_ids' in request.body && request.body.file_ids, ['donors.csv', 'gifts.csv']);
  assert.equal(request.body.name, 'Donor gifts');
  assert.equal(request.body.relationship_context?.data_description, 'Charitable donations');
  assert.equal(request.body.relationship_context?.instructions, 'Completed gifts only');
  assert.equal(request.body.relationship_context?.combine_strategy, 'portfolio');
  assert.equal(request.body.relationship_context?.analysis_mode, 'combined');
  assert.deepEqual(request.body.cleaning, { mode: 'raw' });
  assert.deepEqual(request.body.relationship_context?.suggestions, generateRelationshipSuggestions(files));
});

test('a single upload retains its original endpoint and empty selections cannot create an analysis', () => {
  const request = analysisUploadRequest([profile('sales.csv', ['revenue'])], '', '', '', true);
  assert.equal(request.path, '/analyses');
  assert.equal('file_id' in request.body && request.body.file_id, 'sales.csv');
  assert.equal('file_ids' in request.body, false);
  assert.equal(request.body.relationship_context?.analysis_mode, 'single');
  assert.equal(request.body.relationship_context?.current_file_name, 'sales.csv');
  assert.deepEqual(request.body.cleaning, { mode: 'clean' });
  assert.throws(() => analysisUploadRequest([], '', '', '', true), /Upload and review/);
});

test('single and combined analyses carry a separate validated guide without adding it as a data file', () => {
  const guide = parseDataGuide(JSON.stringify({ version: 1, fields: [{ source_table: 'donors.csv',
    source_column: 'segment', label: 'Donor group', values: [{ value: 'H', label: 'High value' }] }] }));
  const donor = profile('donors.csv', ['donor_id', 'segment']);
  const gift = profile('gifts.csv', ['donor_id', 'amount']);
  for (const files of [[donor], [donor, gift]]) {
    const request = analysisUploadRequest(files, '', '', '', true, guide);
    assert.deepEqual(request.body.relationship_context?.data_dictionary, guide);
    const contextualFiles = request.body.relationship_context?.files;
    assert.ok(Array.isArray(contextualFiles));
    assert.equal(contextualFiles.length, files.length);
    assert.deepEqual('file_ids' in request.body ? request.body.file_ids : [request.body.file_id], files.map(file => file.id));
  }
});

test('an invalid guide is rejected separately from the profiled data queue', async () => {
  const queue = addUploadAssets([], [asset('donors.csv'), asset('gifts.csv')]);
  await assert.rejects(readDataGuide({ name: 'guide.json', text: async () => '{bad' }), /valid JSON guide/);
  const uploaded: string[] = [];
  await profileUploadQueue(queue, async file => { uploaded.push(file.name); return profile(file.name, ['donor_id']); }, () => {}, () => {});
  assert.deepEqual(uploaded, ['donors.csv', 'gifts.csv']);
});
