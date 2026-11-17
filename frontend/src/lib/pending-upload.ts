// Stashes one file in IndexedDB while a visitor goes through sign-up, so
// the landing page can resume the upload after they return signed-in.
//
// IndexedDB stores Blobs/Files natively, which sessionStorage cannot. Every
// accessor wraps the IDB open in try/catch: private windows, cleared site
// data, and storage quota refusals must not break the landing page.

const DB_NAME = "vesquiri-pending-upload"
const STORE = "files"
const KEY = "current"
// Replay a stash only within half an hour of the drop. Older entries are
// almost certainly from a different intent and are discarded on sight.
const MAX_AGE_MS = 30 * 60 * 1000

interface StashRecord {
  file: File
  name: string
  storedAt: number
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("IndexedDB unavailable"))
      return
    }
    const req = indexedDB.open(DB_NAME, 1)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE)
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error ?? new Error("IndexedDB open failed"))
  })
}

function wrapRequest<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error ?? new Error("IndexedDB request failed"))
  })
}

export async function stashPendingUpload(file: File): Promise<boolean> {
  try {
    const db = await openDb()
    try {
      const tx = db.transaction(STORE, "readwrite")
      const store = tx.objectStore(STORE)
      const record: StashRecord = {
        file,
        name: file.name,
        storedAt: Date.now(),
      }
      await wrapRequest(store.put(record, KEY))
      await new Promise<void>((resolve, reject) => {
        tx.oncomplete = () => resolve()
        tx.onabort = () => reject(tx.error ?? new Error("IndexedDB tx aborted"))
        tx.onerror = () => reject(tx.error ?? new Error("IndexedDB tx error"))
      })
      return true
    } finally {
      db.close()
    }
  } catch {
    return false
  }
}

/**
 * Removes and returns the stashed file, if any that is still within the
 * replay window. Returns null in every other case (nothing stashed, too
 * old, IndexedDB unavailable). Always clears whatever was there.
 */
export async function takePendingUpload(): Promise<File | null> {
  try {
    const db = await openDb()
    try {
      const tx = db.transaction(STORE, "readwrite")
      const store = tx.objectStore(STORE)
      const record = (await wrapRequest(
        store.get(KEY) as IDBRequest<StashRecord | undefined>
      )) ?? null
      await wrapRequest(store.delete(KEY))
      await new Promise<void>((resolve, reject) => {
        tx.oncomplete = () => resolve()
        tx.onabort = () => reject(tx.error ?? new Error("IndexedDB tx aborted"))
        tx.onerror = () => reject(tx.error ?? new Error("IndexedDB tx error"))
      })
      if (!record) return null
      if (!(record.file instanceof File)) return null
      if (Date.now() - record.storedAt > MAX_AGE_MS) return null
      return record.file
    } finally {
      db.close()
    }
  } catch {
    return null
  }
}

export async function clearPendingUpload(): Promise<void> {
  try {
    const db = await openDb()
    try {
      const tx = db.transaction(STORE, "readwrite")
      await wrapRequest(tx.objectStore(STORE).delete(KEY))
      await new Promise<void>((resolve) => {
        tx.oncomplete = () => resolve()
        tx.onabort = () => resolve()
        tx.onerror = () => resolve()
      })
    } finally {
      db.close()
    }
  } catch {
    // Nothing to do; the stash either never existed or storage is denied.
  }
}
