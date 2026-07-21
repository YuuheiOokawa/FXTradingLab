import { NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE_NAME, verifySessionToken } from "@/lib/session";

/**
 * Single-shared-secret login gate (docs/11_SECURITY.md "BFF migration").
 *
 * Not a multi-user auth system — this app targets one operator. Its job is
 * only to make sure an internet-exposed deployment isn't reachable by an
 * anonymous visitor who stumbles on the URL: every route except /login (and
 * the login/logout API routes themselves) requires a valid, unexpired
 * `fxlab_session` cookie. When `APP_API_TOKEN` is unset (local development),
 * this middleware no-ops entirely.
 *
 * This also gates `/api/backend/*` (the BFF proxy) and `/api/ws-ticket` —
 * both are ordinary paths under this same matcher, so an unauthenticated
 * request never reaches either handler, let alone the real backend.
 *
 * If `APP_API_TOKEN` is set but `SESSION_SECRET` isn't, this still gates
 * everything (fail closed) but login can never succeed (session-login
 * returns 500) — a misconfiguration, not a bypass; see that route's file.
 */

const TOKEN = process.env.APP_API_TOKEN;
const SESSION_SECRET = process.env.SESSION_SECRET;
// /api/session-login and /api/session-logout must stay reachable pre-auth —
// they're how the session cookie above gets set/cleared in the first place;
// gating them too would make login impossible.
const PUBLIC_PATHS = ["/login", "/api/session-login", "/api/session-logout"];

export async function middleware(request: NextRequest) {
  if (!TOKEN) return NextResponse.next();

  const { pathname } = request.nextUrl;
  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) return NextResponse.next();

  const cookieValue = request.cookies.get(SESSION_COOKIE_NAME)?.value;
  if (SESSION_SECRET && (await verifySessionToken(cookieValue, SESSION_SECRET))) {
    return NextResponse.next();
  }

  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("next", pathname);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
