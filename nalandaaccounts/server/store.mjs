// Two stores with the same four methods: an in-memory one for tests and local runs, and Netlify Blobs for real.

export function memoryStore() {
  const m = new Map();
  return {
    async get(key) { return m.has(key) ? structuredClone(m.get(key)) : null; },
    async set(key, value) { m.set(key, structuredClone(value)); },
    async delete(key) { m.delete(key); },
    async list(prefix) { return [...m.keys()].filter((k) => k.startsWith(prefix)).sort(); },
    _size: () => m.size,
  };
}

export async function blobsStore() {
  const { getStore } = await import("@netlify/blobs");
  // strong consistency: a changed password or a disabled user must take effect at once
  const s = getStore({ name: "nalandaaccounts", consistency: "strong" });
  return {
    get: (key) => s.get(key, { type: "json" }),
    set: (key, value) => s.setJSON(key, value),
    delete: (key) => s.delete(key),
    async list(prefix) {
      const { blobs } = await s.list({ prefix });
      return blobs.map((b) => b.key);
    },
  };
}
