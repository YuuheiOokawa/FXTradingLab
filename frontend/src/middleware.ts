import { NextRequest, NextResponse } from "next/server";

/**
 * Single-shared-secret login gate (docs/11_SECURITY.md "Frontend login gate").
 *
 * Not a multi-user auth system — this app targets one operator. Its job is
 * only to make sure an internet-exposed deployment isn't reachable by an
 * anonymous visitor who stumbles on the URL: every route except /login
 * requires a `fxlab_token` cookie matching NEXT_PUBLIC_APP_API_TOKEN (the same
 * token already used for REST/WebSocket auth — see src/lib/api.ts). When that
 * env var is unset (local development), this middleware no-ops entirely.
 */

const TOKEN = process.env.NEXT_PUBLIC_APP_API_TOKEN;
const COOKIE_NAME = "fxlab_token";
const PUBLIC_PATHS = ["/login"];

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
