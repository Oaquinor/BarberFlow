"use strict";

const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "./browser-tests",
  testMatch: "**/*.spec.js",
  fullyParallel: true,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:4173",
    browserName: "chromium",
    serviceWorkers: "block",
    trace: "retain-on-failure",
  },
  webServer: {
    command: process.platform === "win32"
      ? "python -m http.server 4173 --bind 127.0.0.1"
      : "python3 -m http.server 4173 --bind 127.0.0.1",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
