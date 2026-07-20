import { NextRequest, NextResponse } from "next/server";

/**
 * Server-side login check (docs/11_SECURITY.md "Frontend login gate").
 *
 * Deliberately compares against `APP_API_TOKEN` — a server-only env var
 * (no `NEXT_PUBLIC_` prefix) that Next.js never inlines into a client
 * bundle — instead of `NEXT_PUBLIC_APP_API_TOKEN`. The previous version of
 * this gate compared the submitted value against `NEXT_PUBLIC_APP_API_TOKEN`
 * directly inside the `/login` page's own client component, which meant the
 * real secret was embedded in that page's JS bundle — and `/login` must
 * always be reachable by an unauthenticated visitor (that's the point of a
 * login page), so anyone could view-source `/login`, fetch its script tag,
 * and read the plaintext token straight out of it without ever knowing it
 * in advance. Moving the comparison here means the value the client can
 * compromise its own bundle to read is never the thing checked for login.
 *
 * The `fxlab_token` cookie this sets is `httpOnly` — client JS (including a
 * compromised/XSS'd page) cannot read it — and its value is only ever
 * written via this response header, never constructed by page code, so it
 * never appears in any file the browser downloads as source.
 */
export async function POST(request: NextRequest) {
  const expected = process.env.APP_API_TOKEN;
  if (!expected) {
    return NextResponse.json({ error: "server not configured" }, { status: 500 });
  }

  const body = await request.json().catch(() => null);
  const submitted = body?.token;
  if (typeof submitted !== "string" || submitted !== expected) {
    return NextResponse.json({ error: "invalid token" }, { status: 401 });
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.set("fxlab_token", submitted, {
    httpOnly: true,
    sameSite: "strict",
    path: "/",
    maxAge: 8 * 60 * 60, // 8 hours — convenience gate, not a full session system
  });
  return response;
}
