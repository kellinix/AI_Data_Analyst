export interface KeyValueStore {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
}

type Manifest = { version: string; count: number };
let sequence = 0;

/** Keep each encrypted value below older iOS Keychain payload limits.
 * A manifest points to a complete version; a failed write preserves the old one. */
export function chunkedStorage(store: KeyValueStore): KeyValueStore {
  const manifestKey = (key: string) => `${key}.manifest`;
  const pieceKey = (key: string, value: Manifest, index: number) => `${key}.${value.version}.${index}`;
  const readManifest = async (key: string): Promise<Manifest | null> => {
    const value = await store.getItem(manifestKey(key));
    if (!value) return null;
    const result = JSON.parse(value) as Manifest;
    if (!Number.isInteger(result.count) || result.count < 0 || result.count > 1000 || !/^[\w-]+$/.test(result.version)) {
      throw new Error('Invalid stored session');
    }
    return result;
  };
  const removePieces = async (key: string, manifest: Manifest | null) => {
    if (manifest) await Promise.all(Array.from({ length: manifest.count }, (_, index) => store.removeItem(pieceKey(key, manifest, index))));
  };
  const adapter: KeyValueStore = {
    async getItem(key) {
      const manifest = await readManifest(key);
      if (!manifest) return null;
      const parts = await Promise.all(Array.from({ length: manifest.count }, (_, index) => store.getItem(pieceKey(key, manifest, index))));
      if (parts.some((part) => part === null)) throw new Error('Stored session is incomplete');
      return parts.join('');
    },
    async setItem(key, value) {
      const previous = await readManifest(key);
      const chunks = Array.from(value.matchAll(/[\s\S]{1,400}/gu), (match) => match[0]);
      if (chunks.length > 1000) throw new Error('Session is too large to store');
      const next = { version: `${Date.now()}-${++sequence}`, count: chunks.length };
      try {
        for (let index = 0; index < chunks.length; index++) await store.setItem(pieceKey(key, next, index), chunks[index]);
        await store.setItem(manifestKey(key), JSON.stringify(next));
      } catch (error) {
        await removePieces(key, next).catch(() => {});
        throw error;
      }
      await removePieces(key, previous).catch(() => {});
    },
    async removeItem(key) {
      const previous = await readManifest(key);
      await store.removeItem(manifestKey(key));
      await removePieces(key, previous);
    },
  };
  // Supabase now refreshes without a shared auth mutex. Serialize this
  // adapter's reads/writes so chunk cleanup cannot race a session read.
  let pending: Promise<void> = Promise.resolve();
  function serial<T>(action: () => Promise<T>): Promise<T> {
    const next = pending.then(action, action);
    pending = next.then(() => {}, () => {});
    return next;
  }
  return {
    getItem: (key) => serial(() => adapter.getItem(key)),
    setItem: (key, value) => serial(() => adapter.setItem(key, value)),
    removeItem: (key) => serial(() => adapter.removeItem(key)),
  };
}
