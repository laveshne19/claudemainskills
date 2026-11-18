// Small helpers shared by the server code. No dependencies.
import { createHash, randomBytes, timingSafeEqual } from "node:crypto";

export const IST_MS = 5.5 * 3600 * 1000;

/** Today's date in India as yyyy-mm-dd. */
export function istDate(nowMs) {
  return new Date(nowMs + IST_MS).toISOString().slice(0, 10);
}

export function daysBetween(isoFrom, isoTo) {
  const a = Date.parse(isoFrom + "T00:00:00Z");
  const b = Date.parse(isoTo + "T00:00:00Z");
  return Math.floor((b - a) / 86400000);
}

export function isIsoDate(s) {
  return typeof s === "string" && /^\d{4}-\d{2}-\d{2}$/.test(s) && !Number.isNaN(Date.parse(s + "T00:00:00Z"));
}

export function round2(n) {
  return Math.round((Number(n) + Number.EPSILON) * 100) / 100;
}

export function safeEqual(a, b) {
  const x = Buffer.from(String(a));
  const y = Buffer.from(String(b));
  if (x.length !== y.length) {
    // still do a comparison so timing does not reveal the length difference
    timingSafeEqual(x, x);
    return false;
  }
  return timingSafeEqual(x, y);
}

export function slug(name) {
  return String(name).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80) || "ledger";
}

/** Stable id for a ledger name. The hash keeps "A & B" and "A and B" apart. */
export function ledgerId(name) {
  return slug(name) + "-" + createHash("sha1").update(String(name)).digest("hex").slice(0, 6);
}

export function validId(id) {
  return typeof id === "string" && /^[a-z0-9-]{1,120}$/.test(id);
}

const READABLE = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789";
/** A temporary password a person can read out over the phone: no 0/O/1/l/I. */
export function tempPassword(len = 12) {
  const bytes = randomBytes(len);
  let out = "";
  for (let i = 0; i < len; i++) out += READABLE[bytes[i] % READABLE.length];
  return out;
}

export function clip(s, n) {
  return String(s ?? "").slice(0, n);
}
