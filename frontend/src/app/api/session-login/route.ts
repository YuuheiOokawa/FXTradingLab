import { NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE_NAME, SESSION_TTL_SECONDS, createSessionToken } from "@/lib/session";

/**
 * Server-side login check (docs/11_SECURITY.md "BFF migration").
 *
 * Compares the submitted password against `APP_API_TOKEN` — a server-only
 * env var (no `NEXT_PUBLIC_` prefix) Next.js never inlines into a client
 * bundle — never against a client-visible copy (an earlier version of this
 * gate compared inside the `/login` page's own client component against
 * `NEXT_PUBLIC_APP_API_TOKEN`, which meant the real secret was embedded in
 * that always-publicly-reachable page's JS bundle).
 *
 * On success this mints a *signed session token* (lib/session.ts) — not the
 * password itself — as the cookie value, so the cookie and the login
 * password are two different secrets: leaking one doesn't hand over the
 * other. The cookie is `httpOnly` (client JS, including a compromised/XSS'd
 * page, cannot read it), `secure` outside local dev, and `sameSite: strict`.
 */
export async function POST(request: NextRequest) {
  const expectedPassword = process.env.APP_API_TOKEN;
  const sessionSecret = process.env.SESSION_SECRET;
  if (!expectedPassword || !sessionSecret) {
    return NextResponse.json({ error: "server not configured" }, { status: 500 });
  }

  const body = await request.json().catch(() => null);
  const submitted = body?.token;
  if (typeof submitted !== "string" || submitted !== expectedPassword) {
    return NextResponse.json({ error: "invalid token" }, { status: 401 });
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE_NAME, await createSessionToken(sessionSecret), {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/",
    maxAge: SESSION_TTL_SECONDS,
  });

  // Audit trail (docs/15_PRODUCTION_READINESS_REVIEW.md "Audit Log") —
  // awaited (unlike a true fire-and-forget) so it reliably completes on a
  // serverless runtime that may suspend background work after the response
  // is sent, but wrapped in try/catch so a backend hiccup here degrades to
  // "no audit entry", never "operator locked out of their own app".
  const backendUrl = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";
  const backendToken = process.env.BACKEND_API_TOKEN;
  try {
    await fetch(`${backendUrl}/api/v1/system/session-event`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(backendToken ? { Authorization: `Bearer ${backendToken}` } : {}),
      },
      body: JSON.stringify({ action: "login" }),
    });
  } catch {
    // best-effort — see comment above
  }

  return response;
}
