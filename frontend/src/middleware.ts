import { NextRequest, NextResponse } from "next/server";

/**
 * Single-shared-secret login gate (docs/11_SECURITY.md "Frontend login gate").
 *
 * Not a multi-user auth system — this app targets one operator. Its job is
 * only to make sure an internet-exposed deployment isn't reachable by an
 * anonymous visitor who stumbles on the URL: every route except /login
 * requires a `fxlab_token` cookie matching APP_API_TOKEN. When that env var
 * is unset (local development), this middleware no-ops entirely.
 *
 * Deliberately reads the server-only `APP_API_TOKEN` (no `NEXT_PUBLIC_`
 * prefix), NOT `NEXT_PUBLIC_APP_API_TOKEN` — this file runs server-side only
 * and is never shipped to the browser either way, but using the server-only
 * var here keeps the value this middleware checks against fully decoupled
 * from the value `lib/api.ts` must embed client-side to call the backend.
 * The login check itself now happens in app/api/session-login/route.ts,
 * also against this same server-only var — see that file's comment for why
 * comparing against the client-visible token (the old behavior) let anyone
 * who merely visited the always-public /login page read the real secret out
 * of its own JS bundle.
 */

const TOKEN = process.env.APP_API_TOKEN;
const COOKIE_NAME = "fxlab_token";
// /api/session-login must stay reachable pre-auth — it's how the cookie
// above gets set in the first place; gating it too would make login
// impossible (nothing could ever obtain the cookie this middleware requires).
const PUBLIC_PATHS = ["/login", "/api/session-login"];

export function middleware(request: NextRequest) {
  if (!TOKEN) return NextResponse.next();

  const { pathname } = request.nextUrl;
  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) return NextResponse.next();

  const cookieToken = request.cookies.get(COOKIE_NAME)?.value;
  if (cookieToken === TOKEN) return NextResponse.next();

  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("next", pathname);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
