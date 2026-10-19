// Projects mirror `100x testplan matrix --work web-ui` (Browserslist `defaults`, resolved
// as a representative set). Device names: https://playwright.dev/docs/test-projects
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  retries: process.env.CI ? 1 : 0, // one retry, and a pass-on-retry is reported as flaky
  reporter: [['html'], ['list']],
  expect: { toHaveScreenshot: { maxDiffPixelRatio: 0.01 } },
  use: { baseURL: process.env.BASE_URL ?? 'http://localhost:3000', trace: 'on-first-retry' },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
    { name: 'edge', use: { ...devices['Desktop Edge'], channel: 'msedge' } },
    { name: 'mobile-safari', use: { ...devices['iPhone 12'] } },
    { name: 'mobile-chrome', use: { ...devices['Pixel 5'] } },
  ],
});
