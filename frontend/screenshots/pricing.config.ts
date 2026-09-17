import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "@playwright/test";

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const port = Number(process.env.PRICING_UI_PORT ?? "4179");

export default defineConfig({
  testDir: ".",
  testMatch: "pricing.spec.ts",
  outputDir: "../test-results/pricing",
  timeout: 60_000,
  workers: 1,
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    browserName: "chromium",
    headless: true,
    viewport: { width: 1440, height: 1100 },
    locale: "en-US",
    timezoneId: "UTC",
  },
  webServer: {
    command: `node node_modules/vite/bin/vite.js --host 127.0.0.1 --port ${port} --strictPort`,
    cwd: process.env.PRICING_UI_ROOT ?? frontendRoot,
    port,
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
