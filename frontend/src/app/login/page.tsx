"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const COOKIE_NAME = "fxlab_token";
// Mirrors src/middleware.ts's TOKEN constant — both read the same build-time
// env var, so a correct submission here always satisfies the middleware check.
const EXPECTED_TOKEN = process.env.NEXT_PUBLIC_APP_API_TOKEN;

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next") ?? "/dashboard";
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!EXPECTED_TOKEN || value !== EXPECTED_TOKEN) {
      setError("トークンが正しくありません。");
      return;
    }
    // 8 hours — this is a single-operator convenience gate, not a session
    // system; re-entering the token periodically is an acceptable trade-off.
    document.cookie = `${COOKIE_NAME}=${encodeURIComponent(value)}; path=/; max-age=${8 * 60 * 60}; samesite=strict`;
    router.push(next);
    router.refresh();
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
        <Button type="submit" className="w-full">
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
