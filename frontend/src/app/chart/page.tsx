"use client";

import { Suspense } from "react";

import { ChartPageClient } from "@/components/chart/chart-page-client";

export default function ChartPage() {
  return (
    <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">読み込み中...</div>}>
      <ChartPageClient />
    </Suspense>
  );
}
