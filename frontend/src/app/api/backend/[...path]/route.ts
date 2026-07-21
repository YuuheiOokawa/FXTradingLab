import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND_INTERNAL_URL = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";
const BACKEND_API_TOKEN = process.env.BACKEND_API_TOKEN;

/**
 * BFF proxy (docs/11_SECURITY.md "BFF migration"): the browser never holds
 * the real backend bearer token — every REST call it makes goes to this
 * same-origin route instead of directly to FastAPI. This handler attaches
 * the real `Authorization` header server-side (from `BACKEND_API_TOKEN`, a
 * server-only env var Next.js never inlines into a client bundle) and
 * forwards the request/response essentially unchanged, so `lib/api.ts`'s
 * response-shape parsing keeps working without modification.
 *
 * Reachability is already gated by `middleware.ts` — `/api/backend/*` is not
 * in `PUBLIC_PATHS`, so a request without a valid session cookie never
 * reaches this handler at all. This file does not re-check the session
 * itself; it only ever runs for an already-authenticated browser.
 *
 * `BACKEND_API_TOKEN` being unset is only tolerated because the backend
 * itself no-ops its own auth check in that same case (development only,
 * `Settings.auth_required`) — omitting the header here simply matches that;
 * outside development the backend requires the token to even boot
 * (app/main.py's lifespan guard), so a missing/wrong token here surfaces
 * immediately as 401s from every proxied call, not a silent bypass.
 */
async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const targetUrl = `${BACKEND_INTERNAL_URL}/api/v1/${path.join("/")}${request.nextUrl.search}`;

  const headers: Record<string, string> = {};
  if (BACKEND_API_TOKEN) headers["Authorization"] = `Bearer ${BACKEND_API_TOKEN}`;
  const contentType = request.headers.get("content-type");
  if (contentType) headers["Content-Type"] = contentType;
  const inboundRequestId = request.headers.get("x-request-id");
  if (inboundRequestId) headers["X-Request-ID"] = inboundRequestId;

  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  const body = hasBody ? await request.text() : undefined;

  let upstream: Response;
  try {
    upstream = await fetch(targetUrl, {
      method: request.method,
      headers,
      body: body || undefined,
      cache: "no-store",
    });
  } catch {
    return NextResponse.json(
      { error: { code: "BACKEND_UNREACHABLE", message: "backend is unreachable" } },
      { status: 502 }
    );
  }

  const responseBody = await upstream.text();
  const responseHeaders = new Headers();
  for (const key of ["content-type", "x-request-id"]) {
    const value = upstream.headers.get(key);
    if (value) responseHeaders.set(key, value);
  }

  return new NextResponse(responseBody, { status: upstream.status, headers: responseHeaders });
}

export { proxy as GET, proxy as POST, proxy as PUT, proxy as DELETE, proxy as PATCH };
