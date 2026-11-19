// Passwords and sessions. Only node:crypto, no third party code.
import { createHmac, randomBytes, scrypt as scryptCb, timingSafeEqual } from "node:crypto";
import { promisify } from "node:util";
import { safeEqual } from "./util.mjs";

const scrypt = promisify(scryptCb);
const PARAMS = { N: 16384, r: 8, p: 1, keylen: 32 };
export const SESSION_DAYS = 7;
export const MIN_PASSWORD = 10;

export async function hashPassword(password) {
  const salt = randomBytes(16);
  const key = await scrypt(password, salt, PARAMS.keylen, { N: PARAMS.N, r: PARAMS.r, p: PARAMS.p });
  return { alg: "scrypt", ...PARAMS, salt: salt.toString("base64"), hash: key.toString("base64") };
}

/** Always does the same amount of work, even for an unknown user, so timing does not reveal who exists. */
const DUMMY = { N: PARAMS.N, r: PARAMS.r, p: PARAMS.p, keylen: PARAMS.keylen, salt: Buffer.alloc(16, 7).toString("base64"), hash: Buffer.alloc(32).toString("base64") };

export async function verifyPassword(password, record) {
  const rec = record || DUMMY;
  const salt = Buffer.from(rec.salt, "base64");
  const want = Buffer.from(rec.hash, "base64");
  const got = await scrypt(String(password), salt, rec.keylen, { N: rec.N, r: rec.r, p: rec.p });
  const ok = got.length === want.length && timingSafeEqual(got, want);
  return Boolean(record) && ok;
}

export function passwordProblem(pw, username = "") {
  if (typeof pw !== "string" || pw.length < MIN_PASSWORD) return `Use at least ${MIN_PASSWORD} characters.`;
  if (pw.length > 200) return "That password is too long.";
  if (username && pw.toLowerCase().includes(username.toLowerCase())) return "The password must not contain your user name.";
  if (/^(.)\1+$/.test(pw)) return "That password is too simple.";
  return null;
}

const b64u = (buf) => Buffer.from(buf).toString("base64url");

/** Signed, expiring session token. Revoked by bumping the user's tokenVersion. */
export function signSession(secret, { u, v }, nowMs) {
  const body = b64u(JSON.stringify({ u, v, iat: Math.floor(nowMs / 1000), exp: Math.floor(nowMs / 1000) + SESSION_DAYS * 86400 }));
  const sig = createHmac("sha256", secret).update(body).digest("base64url");
  return `${body}.${sig}`;
}

export function readSession(secret, token, nowMs) {
  if (typeof token !== "string" || token.length > 1000) return null;
  const [body, sig] = token.split(".");
  if (!body || !sig) return null;
  const want = createHmac("sha256", secret).update(body).digest("base64url");
  if (!safeEqual(sig, want)) return null;
  let data;
  try { data = JSON.parse(Buffer.from(body, "base64url").toString("utf8")); } catch { return null; }
  if (!data || typeof data.u !== "string" || !Number.isInteger(data.v) || data.exp * 1000 < nowMs) return null;
  return data;
}

export function parseCookies(header) {
  const out = {};
  for (const part of String(header || "").split(";")) {
    const i = part.indexOf("=");
    if (i > 0) out[part.slice(0, i).trim()] = decodeURIComponent(part.slice(i + 1).trim());
  }
  return out;
}
