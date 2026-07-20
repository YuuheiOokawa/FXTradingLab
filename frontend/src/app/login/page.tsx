"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next") ?? "/dashboard";
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      // Verified server-side (app/api/session-login/route.ts) against a
      // server-only env var — see docs/11_SECURITY.md "Frontend login gate"
      // for why this must not be a client-side comparison.
      const res = await fetch("/api/session-login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: value }),
      });
      if (!res.ok) {
        setError("トークンが正しくありません。");
        return;
      }
      router.push(next);
      router.refresh();
    } catch {
      setError("ログインに失敗しました。時間をおいて再度お試しください。");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <form onSubmit={handleSubmit} className="w-full max-w-sm rounded-lg border border-border bg-card p-6 shadow-sm">
        <div className="mb-6 flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-sm font-bold text-primary-foreground">
            FX
          </div>
          <span className="text-base font-semibold">FX Trading Lab</span>
        </div>
        <p className="mb-4 text-sm text-muted-foreground">
          このアプリはトークン認証で保護されています。アクセストークンを入力してください。
        </p>
        <Input
          type="password"
          autoFocus
          placeholder="APP_API_TOKEN"
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            setError(null);
          }}
          className="mb-2"
        />
        {error && <p className="mb-2 text-xs text-sell">{error}</p>}
        <Button type="submit" className="w-full" disabled={submitting}>
          ログイン
        </Button>
      </form>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
