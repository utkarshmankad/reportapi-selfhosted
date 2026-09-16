import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 60_000,
  use: {
    baseURL: process.env.SMOKE_UI_URL || "http://127.0.0.1:18080",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  reporter: "list",
});
