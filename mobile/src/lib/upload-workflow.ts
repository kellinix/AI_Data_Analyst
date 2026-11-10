import type { DocumentPickerAsset } from 'expo-document-picker';
import type { CreateAnalysisRequest, CreateCombinedAnalysisRequest, UploadedFile } from '../generated/contracts';
import { generateRelationshipSuggestions, getColumnNames } from '../generated/upload-relationships';

export const supportedFile = /\.(csv|xlsx?|json|parquet|tsv)$/i;
const maximumFileBytes = 512 * 1024 * 1024;

export type QueuedDocument = {
  id: string;
  asset: DocumentPickerAsset;
  uploaded?: UploadedFile;
};

export function addUploadAssets(queue: QueuedDocument[], assets: DocumentPickerAsset[], remainingBytes?: number): QueuedDocument[] {
  const next = [...queue];
  const existing = new Set(queue.map(item => item.id));
  for (const asset of assets) {
    const id = JSON.stringify([asset.name, asset.size ?? null, asset.lastModified]);
    if (existing.has(id)) continue;
    if (!supportedFile.test(asset.name)) throw new Error('Choose CSV, Excel, JSON, Parquet, or TSV files');
    if (asset.size != null && asset.size > maximumFileBytes) throw new Error(`${asset.name} is larger than 512 MB`);
    existing.add(id);
    next.push({ id, asset });
  }
  const pendingBytes = next.filter(item => !item.uploaded).reduce((sum, item) => sum + (item.asset.size ?? 0), 0);
  if (remainingBytes != null && pendingBytes > Math.max(0, remainingBytes)) {
    throw new Error('These files exceed your remaining storage allowance');
  }
  return next;
}

export async function profileUploadQueue(
  queue: QueuedDocument[],
  upload: (asset: DocumentPickerAsset, onProgress: (progress: number) => void) => Promise<UploadedFile>,
  onProgress: (id: string, progress: number) => void,
  onUploaded: (id: string, file: UploadedFile) => void,
): Promise<void> {
  for (const item of queue) {
    if (item.uploaded) continue;
    onProgress(item.id, 0);
    const file = await upload(item.asset, progress => onProgress(item.id, progress));
    onUploaded(item.id, file);
  }
}

export function analysisUploadRequest(files: UploadedFile[], name: string, context: string, instructions: string, clean: boolean): {
  path: string;
  body: CreateAnalysisRequest | CreateCombinedAnalysisRequest;
} {
  if (files.length === 0) throw new Error('Upload and review your files before creating an analysis');
  const combined = files.length > 1;
  const relationshipContext = {
    files: files.map(file => ({ id: file.id, name: file.original_filename, row_count: file.row_count,
      column_count: file.column_count, columns: getColumnNames(file) })),
    suggestions: generateRelationshipSuggestions(files),
    data_description: context.trim() || null,
    instructions: instructions.trim() || null,
    analysis_mode: combined ? 'combined' : 'single',
    ...(combined ? { combine_strategy: 'portfolio' } : { current_file_id: files[0].id, current_file_name: files[0].original_filename }),
  };
  return {
    path: combined ? '/analyses/combined' : '/analyses',
    body: {
      ...(combined ? { file_ids: files.map(file => file.id) } : { file_id: files[0].id }),
      name: name.trim() || undefined,
      relationship_context: relationshipContext,
      cleaning: { mode: clean ? 'clean' : 'raw' },
    },
  };
}
