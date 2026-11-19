// Netlify entry point. All API routes live in server/core.mjs.
import { createApp } from "../../server/core.mjs";
import { blobsStore } from "../../server/store.mjs";

let app;

export default async (req) => {
  if (!app) {
    app = createApp({
      store: await blobsStore(),
      env: { SESSION_SECRET: Netlify.env.get("SESSION_SECRET"), SYNC_KEY: Netlify.env.get("SYNC_KEY") },
    });
  }
  return app(req);
};

export const config = { path: "/api/*" };
