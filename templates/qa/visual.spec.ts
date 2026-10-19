// Visual regression against APPROVED baselines (the signed-off mock, captured once).
// API: https://playwright.dev/docs/test-snapshots, options:
// https://playwright.dev/docs/api/class-pageassertions#page-assertions-to-have-screenshot-1
//
// Baseline update policy: never run `npx playwright test --update-snapshots` to make a red
// build green. A baseline changes only in a PR whose description links the approved design
// change, and a reviewer compares the old and new PNGs in the diff before approving.
// Baselines are per browser and OS (e.g. home-chromium-linux.png): generate them in the
// same container CI uses, or every run will differ.
import { test, expect } from '@playwright/test';

test('<feature>/AC-1 <screen> matches the approved design', { tag: '@visual' }, async ({ page }) => {
  await page.goto('/<route>');
  await expect(page).toHaveScreenshot('<screen>.png', {
    fullPage: true,
    animations: 'disabled',
    threshold: 0.2,            // per-pixel YIQ colour tolerance (Playwright default)
    maxDiffPixelRatio: 0.01,   // at most 1% of pixels may differ
    mask: [                    // dynamic regions: timestamps, avatars, ads, counters
      page.getByTestId('relative-time'),
      page.getByRole('img', { name: /avatar/i }),
    ],
  });
});
