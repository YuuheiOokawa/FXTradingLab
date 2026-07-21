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
  return response;
}
