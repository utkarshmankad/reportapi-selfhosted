import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
    coverage: {
      provider: "v8",
      include: [
        "components/**/*.{ts,tsx}",
        "lib/**/*.ts",
        "app/page.tsx",
        "app/api/**/route.ts",
      ],
      reporter: ["text", "lcov", "html"],
      thresholds: { lines: 80, functions: 80, branches: 80, statements: 80 },
    },
  },
});
