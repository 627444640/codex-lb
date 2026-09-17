import { mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

import {
  createAccountSummary,
  createDashboardAuthSession,
  createDashboardOverview,
  createDashboardProjections,
  createDashboardSettings,
  createRequestLogEntry,
  createRequestLogFilterOptions,
  createRequestLogsResponse,
  createTelemetryConsent,
} from "../src/test/mocks/factories";

const evidenceDir = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../openspec/changes/integrate-official-token-pricing/evidence",
);
const phase = process.env.PRICING_UI_PHASE === "before" ? "before" : "after";
const account = createAccountSummary({
  accountId: "pricing-fixture-account",
  email: "pricing@example.com",
  displayName: "Synthetic pricing account",
});
const baseRow = {
  accountId: account.accountId,
  apiKeyName: "Synthetic key",
  requestedAt: "2026-09-17T10:00:00Z",
  pricingVersion: "catalog:synthetic-prices-v1",
  costBreakdown: null,
};
const requests = [
  createRequestLogEntry({
    ...baseRow,
    requestId: "pricing-fixture-estimated",
    model: "gpt-5.6-sol",
    actualModel: "gpt-5.6-luna",
    tokens: 1200,
    inputTokens: 1000,
    outputTokens: 200,
    outputTokensRaw: 200,
    cachedInputTokens: 200,
    cacheWriteTokens: 300,
    costUsd: 0.000419,
    costStatus: "estimated",
    costBreakdown: {
      inputUsd: 0.0001, cachedInputUsd: 0.000004,
      cacheWriteUsd: 0.000075, outputUsd: 0.00024, totalUsd: 0.000419,
    },
  }),
  createRequestLogEntry({
    ...baseRow,
    requestId: "pricing-fixture-unknown-rate",
    model: "gpt-5.6-sol",
    serviceTier: "ultrafast",
    actualServiceTier: "ultrafast",
    costUsd: null,
    costStatus: "unknown_pricing",
  }),
  createRequestLogEntry({
    ...baseRow,
    requestId: "pricing-fixture-historical",
    model: "gpt-5.2-codex",
    costUsd: 4.321234,
    costStatus: "historical",
    pricingVersion: "catalog:synthetic-previous-prices",
  }),
  createRequestLogEntry({
    ...baseRow,
    requestId: "pricing-fixture-incomplete",
    model: "gpt-6-astra",
    costUsd: 0.00000002,
    costStatus: "incomplete_usage",
  }),
  createRequestLogEntry({
    ...baseRow,
    requestId: "pricing-fixture-unknown-model",
    model: "unpublished-model",
    costUsd: null,
    costStatus: "unknown_model",
  }),
  createRequestLogEntry({
    ...baseRow,
    requestId: "pricing-fixture-missing-usage",
    model: "gpt-5.4",
    tokens: null,
    inputTokens: null,
    outputTokens: null,
    cachedInputTokens: null,
    costUsd: null,
    costStatus: "missing_usage",
  }),
];

test("request pricing uses synthetic evidence without contacting a backend", async ({ page, baseURL }) => {
  mkdirSync(evidenceDir, { recursive: true });
  const unexpectedApiPaths = new Set<string>();
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    // Deny every external origin, including any production or upstream service.
    if (url.origin !== baseURL) return route.abort();
    const payloads: Record<string, unknown> = {
      "/api/dashboard-auth/session": createDashboardAuthSession(),
      "/api/dashboard/overview": createDashboardOverview({ accounts: [account] }),
      "/api/dashboard/projections": createDashboardProjections(),
      "/api/request-logs/options": createRequestLogFilterOptions(),
      "/api/request-logs": createRequestLogsResponse(requests, requests.length, false),
      "/api/accounts": { accounts: [account] },
      "/api/settings": createDashboardSettings(),
      "/api/settings/telemetry": createTelemetryConsent({ state: "disabled", active: false }),
      "/api/runtime/version": {
        currentVersion: "synthetic-fixture", latestVersion: "synthetic-fixture", updateAvailable: false,
        checkedAt: "2026-09-17T10:00:00Z", source: "fixture", releaseUrl: "https://example.com/releases",
      },
      "/api/models": { models: [] },
      "/health": { status: "ok" },
      "/health/ready": { status: "ok" },
    };
    if (url.pathname in payloads) {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(payloads[url.pathname]) });
    }
    if (["/api/", "/v1/", "/backend-api/", "/health"].some((prefix) => url.pathname.startsWith(prefix))) {
      if (!url.pathname.startsWith("/api/conversation-archive/")) unexpectedApiPaths.add(url.pathname);
      return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { code: "not_found", message: "Synthetic fixture has no archive" } }) });
    }
    return route.continue();
  });
  await page.addInitScript(() => {
    localStorage.setItem("codex-lb-theme", "light");
    localStorage.setItem("i18nextLng", "en");
  });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/dashboard?view=request-logs", { waitUntil: "networkidle" });
  await expect(page.getByRole("button", { name: "View Details" })).toHaveCount(requests.length);
  await page.addStyleTag({ content: "*, *::before, *::after { animation: none !important; transition: none !important; }" });
  if (phase === "after") {
    await expect(page.getByText("$0.000419", { exact: true })).toBeVisible();
    await expect(page.getByText("Rate unknown", { exact: true })).toBeVisible();
    await expect(page.getByText("Historical estimate", { exact: true })).toBeVisible();
  } else {
    await expect(page.getByRole("table").last().getByText("$0.00", { exact: true }).first()).toBeVisible();
  }
  await page.getByRole("table").last().screenshot({ path: path.join(evidenceDir, `pricing-table-${phase}.png`) });
  if (phase === "after") {
    await page.setViewportSize({ width: 1440, height: 1600 });
    await page.getByRole("button", { name: "View Details" }).first().click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText("catalog:synthetic-prices-v1")).toBeVisible();
    await expect(dialog).toContainText("300 Cache write ($0.000075)");
    await expect(dialog).toContainText("gpt-5.6-luna");
    await dialog.screenshot({ path: path.join(evidenceDir, "pricing-details-after.png") });
    await dialog.getByRole("button", { name: "Close", exact: true }).first().click();
    await page.getByRole("button", { name: "View Details" }).nth(1).click();
    await expect(dialog).toContainText("no verified rate is available for this service tier or context length");
    await expect(dialog).not.toContainText("$0.00");
    await dialog.screenshot({ path: path.join(evidenceDir, "pricing-unknown-rate-after.png") });
  }
  expect([...unexpectedApiPaths]).toEqual([]);
});
