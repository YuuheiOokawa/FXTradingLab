import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND_INTERNAL_URL = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";
const BACKEND_API_TOKEN = process.env.BACKEND_API_TOKEN;

/**
 * Mints a short-lived, single-use WebSocket ticket on behalf of an
 * already-session-authenticated browser (docs/11_SECURITY.md "BFF
 * migration"). Gated by `middleware.ts` exactly like `/api/backend/*` — a
 * request without a valid session cookie never reaches this handler.
 *
 * The browser calls this once per (re)connection attempt, then opens the
 * WebSocket directly to the backend (not proxied through Next.js — binary
 * WS framing through an HTTP proxy layer isn't worth the added latency/
 * complexity here) with `?ticket=<value>`. See app/ws/tickets.py for why a
 * one-shot, ~45s-lived ticket is safe to hand the browser even though the
 * old long-lived shared token was not.
 *
 * `BACKEND_API_TOKEN` being unset is only tolerated because the backend's
 * own auth check no-ops in that same case (development only) — see the
 * matching comment in app/api/backend/[...path]/route.ts.
 */
export async function POST() {
  const headers: Record<string, string> = {};
  if (BACKEND_API_TOKEN) headers["Authorization"] = `Bearer ${BACKEND_API_TOKEN}`;

  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND_INTERNAL_URL}/api/v1/system/ws-ticket`, {
      method: "POST",
      headers,
      cache: "no-store",
    });
  } catch {
    return NextResponse.json(
      { error: { code: "BACKEND_UNREACHABLE", message: "backend is unreachable" } },
      { status: 502 }
    );
  }

  const body = await upstream.text();
  return new NextResponse(body, {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
