/**
 * Signed session cookie for the single-principal web app.
 *
 * The API token never reaches the browser; this cookie only proves the visitor
 * passed the login. Uses Web Crypto so the same code works in the Edge
 * middleware and in Node server actions.
 */

const enc = new TextEncoder();

export const SESSION_COOKIE = "job_os_session";
const MAX_AGE_SECONDS = 60 * 60 * 12; // 12h

function toHex(buf: ArrayBuffer): string {
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** Constant-time string compare, so a wrong token cannot be timed out char by char. */
function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

async function hmacKey(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
}

async function sign(payload: string, secret: string): Promise<string> {
  const key = await hmacKey(secret);
  return toHex(await crypto.subtle.sign("HMAC", key, enc.encode(payload)));
}

/** Issue a session token that expires. */
export async function issueSession(secret: string): Promise<string> {
  const expires = Date.now() + MAX_AGE_SECONDS * 1000;
  const payload = `v1.${expires}`;
  return `${payload}.${await sign(payload, secret)}`;
}

/** Verify signature AND expiry. */
export async function verifySession(
  token: string | undefined,
  secret: string,
): Promise<boolean> {
  if (!token || !secret) return false;
  const parts = token.split(".");
  if (parts.length !== 3) return false;
  const [version, expires, mac] = parts;
  if (version !== "v1") return false;

  const expected = await sign(`${version}.${expires}`, secret);
  if (!safeEqual(mac, expected)) return false;

  const exp = Number(expires);
  return Number.isFinite(exp) && Date.now() < exp;
}

export const sessionCookieOptions = {
  httpOnly: true, // not readable by page scripts
  sameSite: "lax" as const,
  secure: process.env.NODE_ENV === "production",
  path: "/",
  maxAge: MAX_AGE_SECONDS,
};
