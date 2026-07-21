import { NextResponse } from "next/server";

import { SESSION_COOKIE_NAME } from "@/lib/session";

/**
 * Clears the session cookie (docs/11_SECURITY.md "BFF migration" — Browser
 * Session Authentication checklist item "Logout"). Since sessions here are
 * stateless signed tokens (lib/session.ts), this cannot force-invalidate a
 * copy of the token an attacker already exfiltrated before it expires — see
 * that file's docstring for why that gap is accepted rather than built out
 * for a single-operator app. What this *does* guarantee: the browser that
 * calls this immediately stops sending any session cookie at all, so the
 * next request from this browser hits the login gate again.
 */
export async function POST() {
  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE_NAME, "", { path: "/", maxAge: 0 });

  // Audit trail — see app/api/session-login/route.ts's matching comment for
  // why this is awaited-but-best-effort.
  const backendUrl = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";
  const backendToken = process.env.BACKEND_API_TOKEN;
  try {
    await fetch(`${backendUrl}/api/v1/system/session-event`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(backendToken ? { Authorization: `Bearer ${backendToken}` } : {}),
      },
      body: JSON.stringify({ action: "logout" }),
    });
  } catch {
    // best-effort — see comment above
  }

  return response;
}
