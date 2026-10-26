import { Platform } from 'react-native';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import type { DocumentPickerAsset } from 'expo-document-picker';
import type { UploadedFile } from '../generated/contracts';
import { config } from './config';
import { accessToken } from './api';
import { ApiError, errorDetail } from './api-core';

export const supportedFile = /\.(csv|xlsx?|json|parquet|tsv)$/i;

export async function uploadDocument(asset: DocumentPickerAsset, onProgress: (progress: number) => void): Promise<UploadedFile> {
  const token = await accessToken();
  if (!token) throw new ApiError('Sign in to upload', 401);
  const url = `${config.apiUrl}/api/v1/uploads`;
  let status: number, body: unknown;
  if (Platform.OS === 'web') {
    if (!asset.file) throw new Error('Please choose the file again');
    const form = new FormData();
    form.append('file', asset.file, asset.name);
    const response = await fetch(url, { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: form });
    status = response.status;
    body = await response.json();
  } else {
    const result = await FileSystem.createUploadTask(url, asset.uri, {
      httpMethod: 'POST', uploadType: FileSystem.FileSystemUploadType.MULTIPART,
      fieldName: 'file', mimeType: asset.mimeType ?? 'application/octet-stream',
      headers: { Authorization: `Bearer ${token}` },
    }, ({ totalBytesSent, totalBytesExpectedToSend }) => {
      if (totalBytesExpectedToSend > 0) onProgress(Math.min(99, Math.round(totalBytesSent / totalBytesExpectedToSend * 100)));
    }).uploadAsync();
    if (!result) throw new Error('Upload was canceled');
    status = result.status;
    try { body = JSON.parse(result.body); } catch { throw new Error('The server returned an invalid upload response'); }
  }
  if (status < 200 || status >= 300) throw new ApiError(errorDetail(body, 'Upload failed. Please retry.'), status);
  onProgress(100);
  return body as UploadedFile;
}

export async function exportReport(id: string, format: 'pdf' | 'excel') {
  const token = await accessToken();
  if (!token) throw new ApiError('Sign in to export', 401);
  const url = `${config.apiUrl}/api/v1/analyses/${encodeURIComponent(id)}/export/${format}`;
  const filename = `zephyr-${id}${format === 'pdf' ? '-visual-report' : ''}-${Date.now()}.${format === 'pdf' ? 'pdf' : 'xlsx'}`;
  if (Platform.OS === 'web') {
    const response = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok) throw new ApiError(errorDetail(await response.json().catch(() => null), 'Export failed'), response.status);
    const objectUrl = URL.createObjectURL(await response.blob());
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = filename;
    link.click();
    setTimeout(() => URL.revokeObjectURL(objectUrl), 10_000);
    return;
  }
  if (!FileSystem.cacheDirectory) throw new Error('File storage is unavailable');
  const destination = FileSystem.cacheDirectory + filename;
  const result = await FileSystem.downloadAsync(url, destination, { headers: { Authorization: `Bearer ${token}` } });
  if (result.status < 200 || result.status >= 300) {
    await FileSystem.deleteAsync(destination, { idempotent: true }).catch(() => {});
    throw new Error(`Export failed (${result.status})`);
  }
  if (!await Sharing.isAvailableAsync()) throw new Error('File sharing is unavailable on this device');
  await Sharing.shareAsync(result.uri, {
    mimeType: format === 'pdf' ? 'application/pdf' : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    UTI: format === 'pdf' ? 'com.adobe.pdf' : 'org.openxmlformats.spreadsheetml.sheet',
  });
}
