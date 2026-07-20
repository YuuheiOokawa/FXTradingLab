import type { Metadata } from "next";
import "./globals.css";

import { Providers } from "./providers";
import { Sidebar } from "@/components/layout/sidebar";
import { TopBar } from "@/components/layout/top-bar";

export const metadata: Metadata = {
  title: "FX Trading Lab",
  description: "FXリアルタイム監視・分析・シミュレーション・バックテスト・トレーディング",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja" className="dark">
      <body className="font-sans antialiased">
        <Providers>
          <div className="flex h-screen w-screen overflow-hidden">
            <Sidebar />
            <div className="flex min-w-0 flex-1 flex-col">
              <TopBar />
              <main className="flex-1 overflow-y-auto p-4 md:p-6">{children}</main>
            </div>
          </div>
        </Providers>
      </body>
    </html>
  );
}
