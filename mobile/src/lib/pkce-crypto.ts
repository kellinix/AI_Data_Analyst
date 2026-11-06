/** The Supabase client uses these Web Crypto operations to create an S256 PKCE challenge. */
export function installPkceCrypto(
  target: { crypto?: unknown },
  native: { getRandomValues: (array: Uint32Array) => Uint32Array; sha256: (data: BufferSource) => Promise<ArrayBuffer> },
) {
  const existing = target.crypto as { getRandomValues?: unknown; subtle?: { digest?: unknown } } | undefined;
  if (typeof existing?.getRandomValues === 'function' && typeof existing.subtle?.digest === 'function') return;

  // Fail closed if the native module is unavailable instead of allowing Math.random or plain PKCE.
  const crypto = {
    getRandomValues: (array: Uint32Array) => native.getRandomValues(array),
    subtle: {
      digest: (algorithm: string, data: BufferSource) => {
        if (algorithm !== 'SHA-256') return Promise.reject(new Error('Unsupported digest algorithm'));
        return native.sha256(data);
      },
    },
  };
  Object.defineProperty(target, 'crypto', { configurable: true, writable: true, value: crypto });
}
