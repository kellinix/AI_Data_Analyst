export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

export function errorDetail(value: unknown, fallback: string): string {
  if (!value || typeof value !== 'object') return fallback;
  const detail = (value as { detail?: unknown }).detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((item) => typeof item?.msg === 'string' ? item.msg : 'Invalid input').join('. ');
  return fallback;
}

export function createApi(baseUrl: string, getToken: () => Promise<string | null>, fetcher: typeof fetch = fetch) {
  return async function request<T>(path: string, options: { method?: string; body?: unknown; timeout?: number; signal?: AbortSignal } = {}): Promise<T> {
    if (!baseUrl) throw new Error('Set the API URL before connecting');
    const token = await getToken();
    if (!token) throw new ApiError('Sign in to continue', 401);
    const controller = new AbortController();
    const abort = () => controller.abort();
    options.signal?.addEventListener('abort', abort);
    if (options.signal?.aborted) controller.abort();
    const timeout = setTimeout(abort, options.timeout ?? 30_000);
    try {
      const response = await fetcher(`${baseUrl}/api/v1${path}`, {
        method: options.method ?? 'GET',
        headers: { Authorization: `Bearer ${token}`, ...(options.body === undefined ? {} : { 'Content-Type': 'application/json' }) },
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        signal: controller.signal,
      });
      if (response.status === 204) return undefined as T;
      const body: unknown = await response.json().catch(() => null);
      if (!response.ok) throw new ApiError(errorDetail(body, `Request failed (${response.status})`), response.status);
      return body as T;
    } catch (error) {
      if (controller.signal.aborted) throw new Error(options.signal?.aborted ? 'Request canceled' : 'The request timed out. Please retry.');
      if (error instanceof ApiError) throw error;
      throw new Error('Could not connect. Check your network and try again.');
    } finally {
      clearTimeout(timeout);
      options.signal?.removeEventListener('abort', abort);
    }
  };
}
