import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.E2E_BASE_URL || "http://127.0.0.1:3000";
const isE2EReportMode = process.env.E2E_REPORT_MODE === "1";
const resolvedPort = (() => {
  try {
    const port = new URL(baseURL).port;
    return port || "3000";
  } catch {
    return "3000";
  }
})();

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./test-results",
  timeout: 30_000,
  expect: {
    timeout: 10_000,
  },
  fullyParallel: true,
  workers: process.env.CI ? 2 : 1,
  retries: process.env.CI ? 2 : 0,
  reporter: [
    ["list"],
    ["html", { open: "never", outputFolder: "playwright-report" }],
    ["json", { outputFile: "test-results/results.json" }],
  ],

  use: {
    baseURL,
    trace: "retain-on-failure",
    video: "retain-on-failure",
    screenshot: isE2EReportMode ? "on" : "only-on-failure",
    headless: true,
  },

  projects: [
    // ── Auth setup (runs first, no storage state) ────────────────
    {
      name: "setup",
      testMatch: /auth\.setup\.ts/,
    },

    // ── Chromium (depends on setup, uses saved auth state) ───────
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        storageState: "e2e/.auth/user.json",
      },
      dependencies: ["setup"],
      testMatch: /\.spec\.ts$/,
    },

    // ── Firefox (depends on setup, uses saved auth state) ────────
    {
      name: "firefox",
      use: {
        ...devices["Desktop Firefox"],
        storageState: "e2e/.auth/user.json",
      },
      dependencies: ["setup"],
      testMatch: /\.spec\.ts$/,
    },
  ],

  webServer: {
    command: `bunx next dev --hostname 0.0.0.0 --port ${resolvedPort}`,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
