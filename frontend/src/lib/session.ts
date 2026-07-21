/**
 * Signed, stateless session tokens (docs/11_SECURITY.md "BFF migration").
 *
 * The cookie this app issues after login is deliberately NOT the raw login
 * password (`APP_API_TOKEN`) — the previous design stored that value
 * verbatim as the cookie, so leaking the cookie (a misconfigured proxy log,
 * a browser extension, XSS despite HttpOnly on some legacy browser) leaked
 * the actual operator password outright. Instead this signs an
 * issued-at/expiry payload with a dedicated `SESSION_SECRET` the browser
 * never has any route to — knowing the session cookie's value tells you
 * nothing about the login password or the backend's `BACKEND_API_TOKEN`.
 *
 * Uses Web Crypto (`crypto.subtle`) rather than Node's `crypto` module so
 * this works unchanged in `middleware.ts`'s Edge runtime.
 *
 * Known limitation, accepted for a single-operator app: this is stateless,
 * so there is no server-side revocation list — "logout" clears the cookie
 * client-side but a copy of a still-valid (un-expired) token stolen before
 * logout remains valid until it expires. True pre-expiry revocation would
 * need a server-side session store (Redis, which the backend already has);
 * documented as a known gap in docs/11_SECURITY.md rather than built here,
 * since adding a stateful store purely for this single-operator app's
 * threat model is disproportionate — see docs/15 "what's still open".
 */

const encoder = new TextEncoder();
const decoder = new TextDecoder();

export const SESSION_COOKIE_NAME = "fxlab_session";
export const SESSION_TTL_SECONDS = 8 * 60 * 60; // 8 hours — matches the previous cookie's maxAge

async function hmacKey(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey("raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, [
    "sign",
    "verify",
  ]);
}

function base64url(bytes: ArrayBuffer | Uint8Array): string {
  const arr = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let str = "";
  arr.forEach((b) => (str += String.fromCharCode(b)));
  return btoa(str).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function base64urlDecode(s: string): Uint8Array<ArrayBuffer> {
  const padded = s.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (s.length % 4)) % 4);
  const str = atob(padded);
  // .slice() forces a plain ArrayBuffer-backed view — TS 5.7+ types
  // Uint8Array.from()'s result as Uint8Array<ArrayBufferLike>, which
  // crypto.subtle's BufferSource params reject.
  return Uint8Array.from(str, (c) => c.charCodeAt(0)).slice();
}

export async function createSessionToken(secret: string): Promise<string> {
  const now = Date.now();
  const payload = JSON.stringify({ iat: now, exp: now + SESSION_TTL_SECONDS * 1000 });
  const payloadB64 = base64url(encoder.encode(payload));
  const key = await hmacKey(secret);
  const signature = await crypto.subtle.sign("HMAC", key, encoder.encode(payloadB64));
  return `${payloadB64}.${base64url(signature)}`;
}

export async function verifySessionToken(token: string | undefined, secret: string): Promise<boolean> {
  if (!token) return false;
  const [payloadB64, sigB64] = token.split(".");
  if (!payloadB64 || !sigB64) return false;
  try {
    const key = await hmacKey(secret);
    const validSignature = await crypto.subtle.verify(
      "HMAC",
      key,
      base64urlDecode(sigB64),
      encoder.encode(payloadB64)
    );
    if (!validSignature) return false;
    const payload = JSON.parse(decoder.decode(base64urlDecode(payloadB64))) as { exp?: number };
    return typeof payload.exp === "number" && payload.exp > Date.now();
  } catch {
    return false;
  }
}
