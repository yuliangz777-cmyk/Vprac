// IndexedDB store for practice recordings. Audio blobs are far too large for
// localStorage, so takes live here and only their ids are kept in app state.

const DB_NAME = 'violinQuestMedia';
const DB_VERSION = 1;
const STORE = 'recordings';

let dbPromise = null;

function openDB() {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    if (!('indexedDB' in window)) { reject(new Error('此瀏覽器不支援 IndexedDB')); return; }
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        const store = db.createObjectStore(STORE, { keyPath: 'id' });
        store.createIndex('dayKey', 'dayKey', { unique: false });
        store.createIndex('createdAt', 'createdAt', { unique: false });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return dbPromise;
}

function tx(mode, fn) {
  return openDB().then((db) => new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE, mode);
    const store = transaction.objectStore(STORE);
    let result;
    try { result = fn(store); } catch (err) { reject(err); return; }
    transaction.oncomplete = () => resolve(result?.result ?? result);
    transaction.onerror = () => reject(transaction.error);
    transaction.onabort = () => reject(transaction.error);
  }));
}

export const recordingsDB = {
  async add(record) {
    await tx('readwrite', (store) => store.put(record));
    return record;
  },
  async update(id, patch) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(STORE, 'readwrite');
      const store = transaction.objectStore(STORE);
      const req = store.get(id);
      req.onsuccess = () => {
        if (!req.result) { resolve(null); return; }
        const next = { ...req.result, ...patch };
        store.put(next);
        resolve(next);
      };
      req.onerror = () => reject(req.error);
    });
  },
  get(id) { return tx('readonly', (store) => store.get(id)); },
  async all() {
    const list = await tx('readonly', (store) => store.getAll());
    return (list || []).sort((a, b) => String(b.createdAt).localeCompare(String(a.createdAt)));
  },
  async byDay(dayKey) {
    const list = await this.all();
    return list.filter((r) => r.dayKey === dayKey);
  },
  remove(id) { return tx('readwrite', (store) => store.delete(id)); },
  clear() { return tx('readwrite', (store) => store.clear()); },
  async usage() {
    try {
      const { usage = 0, quota = 0 } = (await navigator.storage?.estimate?.()) || {};
      return { usage, quota };
    } catch { return { usage: 0, quota: 0 }; }
  },
};
