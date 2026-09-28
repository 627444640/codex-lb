import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

import { AuthSessionSchema } from "../src/features/auth/schemas";
import { DashboardProjectionsSchema } from "../src/features/dashboard/schemas";
import type {
  Announcement,
  AnnouncementUpdate,
  StatusEmailUpdate,
} from "../src/features/settings/status-page-api";

const REQUIRED_API_PATHS = [
  "/api/dashboard-auth/session",
  "/api/dashboard/overview",
  "/api/dashboard/projections",
  "/api/request-logs/options",
  "/api/request-logs",
] as const;

test("the built dashboard accepts real backend responses", async ({ page }) => {
  const apiFailures: string[] = [];
  const telemetryRequests: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/settings/telemetry")) {
      telemetryRequests.push(request.url());
    }
  });
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];

  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  });
  page.on("pageerror", (error) => {
    pageErrors.push(error.message);
  });
  page.on("requestfailed", (request) => {
    const path = new URL(request.url()).pathname;
    if (path.startsWith("/api/")) {
      apiFailures.push(
        `${request.method()} ${path}: ${request.failure()?.errorText ?? "request failed"}`,
      );
    }
  });
  page.on("response", (response) => {
    const path = new URL(response.url()).pathname;
    if (!path.startsWith("/api/")) {
      return;
    }
    if (!response.ok()) {
      apiFailures.push(
        `${response.request().method()} ${path}: HTTP ${response.status()}`,
      );
    }
  });

  // Intentionally do not register page.route handlers: every response must
  // come from the uvicorn/FastAPI process started by the smoke harness.
  const requiredResponsesPromise = Promise.all(
    REQUIRED_API_PATHS.map((requiredPath) =>
      page.waitForResponse(
        (response) => new URL(response.url()).pathname === requiredPath,
      ),
    ),
  );
  await page.goto("/dashboard", { waitUntil: "domcontentloaded" });
  const requiredResponses = await requiredResponsesPromise;

  for (const response of requiredResponses) {
    expect(
      response.ok(),
      `${response.request().method()} ${new URL(response.url()).pathname}`,
    ).toBe(true);
  }
  const sessionResponse = requiredResponses[0];
  AuthSessionSchema.parse(await sessionResponse.json());
  const projectionsResponse = requiredResponses.find(
    (response) =>
      new URL(response.url()).pathname === "/api/dashboard/projections",
  );
  if (!projectionsResponse) {
    throw new Error("Dashboard projections response was not captured");
  }
  DashboardProjectionsSchema.parse(await projectionsResponse.json());

  await expect(
    page.getByRole("heading", { name: "Dashboard", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("No accounts connected yet", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("No requests yet", { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);

  await page.waitForLoadState("networkidle");
  expect(telemetryRequests).toEqual([]);
  await expect(
    page.getByRole("dialog", { name: "Anonymous telemetry" }),
  ).toHaveCount(0);
  expect(apiFailures).toEqual([]);
  expect(pageErrors).toEqual([]);
  expect(consoleErrors).toEqual([]);
});

test("status settings remain disconnected without a monitor connector", async ({
  page,
}) => {
  const responsePromise = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/api/settings/status-page",
  );
  await page.goto("/settings", { waitUntil: "domcontentloaded" });
  const response = await responsePromise;
  expect(response.ok()).toBe(true);
  expect(await response.json()).toMatchObject({
    available: false,
    email: null,
  });
  const section = page.locator("#status-page-settings");
  await expect(
    section.getByRole("heading", { name: "Email alerts and announcements" }),
  ).toBeVisible();
  await expect(
    section.getByText("The status service is not connected yet."),
  ).toBeVisible();
  await expect(
    section.getByRole("button", { name: "Save email settings" }),
  ).toHaveCount(0);
});

test("status controls preserve secrets and announcement schedules across supported viewports", async ({
  page,
}) => {
  // Only the status API uses synthetic responses. Session, Settings and built
  // assets still come from the isolated backend. No mail or public notice is sent.
  let email = {
    enabled: false,
    host: "smtp.example.invalid",
    port: 465,
    tls: "ssl",
    sender: "sender@example.invalid",
    username: "sender@example.invalid",
    recipients: ["recipient@example.invalid"],
    passwordConfigured: true,
  };
  const notices: Announcement[] = [];
  const emailWrites: StatusEmailUpdate[] = [];
  const noticeWrites: AnnouncementUpdate[] = [];
  await page.route("**/api/settings/status-page**", async (route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    if (request.method() === "GET") {
      await route.fulfill({
        json: { available: true, email, notices, events: [] },
      });
    } else if (pathname.endsWith("/email")) {
      const body = request.postDataJSON() as StatusEmailUpdate;
      emailWrites.push(body);
      const configuration = { ...body };
      delete configuration.password;
      email = { ...email, ...configuration, passwordConfigured: true };
      await route.fulfill({ json: email });
    } else {
      const body = request.postDataJSON() as AnnouncementUpdate;
      noticeWrites.push(body);
      const notice: Announcement = {
        ...body,
        id: 1,
        createdAt: "2026-09-29T00:00:00Z",
        updatedAt: "2026-09-29T00:00:00Z",
      };
      notices.splice(0, notices.length, notice);
      await route.fulfill({
        status: request.method() === "POST" ? 201 : 200,
        json: { id: 1 },
      });
    }
  });
  await page.goto("/settings", { waitUntil: "domcontentloaded" });
  const section = page.locator("#status-page-settings");
  await section.getByLabel("Sender address").fill("alerts@example.invalid");
  await expect(section.getByLabel("SMTP authorization code")).toHaveValue("");
  await section.getByRole("button", { name: "Save email settings" }).click();
  await expect.poll(() => emailWrites.length).toBe(1);
  expect(emailWrites[0]).not.toHaveProperty("password");

  await section
    .getByLabel("Announcement title")
    .fill("Synthetic maintenance notice");
  await section
    .getByLabel("Announcement body")
    .fill("This is a local integration-test announcement.");
  await section.locator("#status-notice-start").fill("2026-10-01T10:00");
  await section.getByRole("button", { name: "Publish announcement" }).click();
  await expect.poll(() => noticeWrites.length).toBe(1);
  expect(noticeWrites[0]).toMatchObject({
    status: "published",
    startsAt: "2026-10-01T02:00:00.000Z",
  });
  await section
    .getByRole("button", { name: "Edit Synthetic maintenance notice" })
    .click();
  await section.getByRole("button", { name: "Withdraw", exact: true }).click();
  await expect.poll(() => noticeWrites.length).toBe(2);
  expect(noticeWrites[1].status).toBe("withdrawn");

  await expect(page.locator("[data-sonner-toast]")).toHaveCount(0);
  for (const [name, width, height] of [
    ["desktop", 1440, 1000],
    ["mobile", 390, 844],
  ] as const) {
    await page.setViewportSize({ width, height });
    await section.scrollIntoViewIfNeeded();
    await expect(section).toBeVisible();
    expect(
      await section.evaluate(
        (element) => element.scrollWidth <= element.clientWidth,
      ),
    ).toBe(true);
    const screenshots = process.env.STATUS_SETTINGS_SCREENSHOT_DIR;
    if (screenshots) {
      await mkdir(screenshots, { recursive: true });
      const box = await section.boundingBox();
      expect(box).not.toBeNull();
      await page.setViewportSize({
        width,
        height: Math.ceil(box!.height) + 180,
      });
      await section.evaluate((element) => {
        window.scrollTo({
          top: element.getBoundingClientRect().top + window.scrollY - 90,
          behavior: "instant",
        });
      });
      await section.screenshot({
        path: path.join(screenshots, `settings-${name}.png`),
      });
    }
  }
});
