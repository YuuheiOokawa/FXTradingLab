/**
 * BFF client (docs/11_SECURITY.md "BFF migration"). REST calls go to this
 * app's own same-origin `/api/backend/*` proxy — never directly to FastAPI,
 * and never with a bearer token this module holds — so nothing here can leak
 * a backend credential to the browser; there isn't one to leak. Auth is the
 * `fxlab_session` cookie (HttpOnly, sent automatically by the browser on a
 * same-origin request), checked by `middleware.ts` before the proxy route
 * ever runs.
 */
export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined),
  };

  const res = await fetch(`/api/backend${path}`, { ...init, headers, cache: "no-store" });
  if (!res.ok) {
    let message = res.statusText;
    let code: string | undefined;
    try {
      const body = await res.json();
      message = body?.detail?.error?.message ?? body?.detail ?? body?.error?.message ?? message;
      code = body?.detail?.error?.code ?? body?.error?.code;
    } catch {
      // ignore body parse failure
    }
    throw new ApiError(message, res.status, code);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

// The browser-reachable origin of the FastAPI WebSocket endpoints — not a
// secret, just a hostname (e.g. wss://api.fxlab.example.com). WS traffic
// connects directly to the backend rather than proxying binary frames
// through Next.js; per-connection auth comes from a short-lived ticket
// (below), never a long-lived credential in the URL.
const WS_BASE = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";

/**
 * Fetches a fresh single-use WS ticket from this app's own `/api/ws-ticket`
 * route (itself gated by the session cookie via middleware.ts) and returns
 * a ready-to-connect WebSocket URL. Must be called again for every
 * (re)connection attempt — a ticket is consumed on first use and expires in
 * ~45s either way (backend/app/ws/tickets.py).
 */
export async function wsUrl(path: string): Promise<string> {
  const res = await fetch("/api/ws-ticket", { method: "POST", cache: "no-store" });
  if (!res.ok) throw new Error("failed to obtain a WebSocket ticket");
  const { ticket } = (await res.json()) as { ticket: string };
  const url = `${WS_BASE}${path}`;
  return `${url}${url.includes("?") ? "&" : "?"}ticket=${encodeURIComponent(ticket)}`;
}
