// Local server for development and tests: the same API, the same page headers, an in-memory store.
//   SESSION_SECRET=... SYNC_KEY=... PORT=8888 node server/local.mjs
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { createApp } from "./core.mjs";
import { memoryStore } from "./store.mjs";
import { PAGE_HEADERS } from "./csp.mjs";

const ROOT = resolve(fileURLToPath(new URL("../site", import.meta.url)));
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon" };

export function startLocal({ port = 0, env = process.env, store = memoryStore(), now, secureCookie = false } = {}) {
  const app = createApp({ store, env: { SESSION_SECRET: env.SESSION_SECRET, SYNC_KEY: env.SYNC_KEY }, now, secureCookie });
  const server = createServer(async (req, res) => {
    try {
      const url = new URL(req.url, "http://localhost");
      if (url.pathname.startsWith("/api/")) {
        const chunks = [];
        for await (const c of req) chunks.push(c);
        const body = chunks.length ? Buffer.concat(chunks) : undefined;
        const headers = new Headers();
        for (const [k, v] of Object.entries(req.headers)) if (v !== undefined) headers.set(k, Array.isArray(v) ? v.join(", ") : v);
        const r = await app(new Request(url, { method: req.method, headers, body: ["GET", "HEAD"].includes(req.method) ? undefined : body }));
        res.writeHead(r.status, Object.fromEntries(r.headers));
        res.end(Buffer.from(await r.arrayBuffer()));
        return;
      }
      let p = normalize(decodeURIComponent(url.pathname));
      if (p === sep || p === "/") p = "/index.html";
      const file = resolve(join(ROOT, p));
      if (!file.startsWith(ROOT + sep)) { res.writeHead(403); return res.end("Forbidden"); }
      const data = await readFile(file);
      res.writeHead(200, { ...PAGE_HEADERS, "Content-Type": TYPES[extname(file)] || "application/octet-stream" });
      res.end(data);
    } catch (e) {
      res.writeHead(e.code === "ENOENT" ? 404 : 500, PAGE_HEADERS);
      res.end(e.code === "ENOENT" ? "Not found" : "Error");
    }
  });
  return new Promise((ok) => server.listen(port, "127.0.0.1", () => ok({ server, store, url: `http://127.0.0.1:${server.address().port}` })));
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const { url } = await startLocal({ port: Number(process.env.PORT || 8888) });
  console.log("Local portal on", url);
}
