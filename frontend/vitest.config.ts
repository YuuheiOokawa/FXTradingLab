import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    // e2e/ holds @playwright/test specs, driven by `npm run test:e2e`
    // against a live stack — vitest's own default include glob (**/*.{test,spec}.*)
    // would otherwise try (and fail) to collect them as unit tests.
    exclude: ["node_modules/**", "e2e/**"],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
