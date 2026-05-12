import { defineConfig } from "vitest/config";
import path from "node:path";

// Vitest config for unit + component tests. The frontend's main dev/build
// flow goes through Next.js; tests bypass Next entirely and run in jsdom
// against the raw component / module code. The `@/` alias mirrors the
// tsconfig path so test imports look identical to app imports.
export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.{test,spec}.{ts,tsx}"],
    css: false,
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./"),
    },
  },
});
