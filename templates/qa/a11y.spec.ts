// Automated WCAG 2.2 AA scan, every tier. Fails on ANY violation; there is no "allowed
// violations" list. Automation finds only part of WCAG — pair it with a keyboard-only and
// screen-reader pass from the exploratory charter.
// API: https://playwright.dev/docs/accessibility-testing; tags:
// https://github.com/dequelabs/axe-core/blob/develop/doc/API.md
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const ROUTES = ['/', '/<critical route>'];

for (const route of ROUTES) {
  test(`${route} has no detectable WCAG 2.2 A/AA violations`, { tag: '@a11y' }, async ({ page }) => {
    await page.goto(route);
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
      .analyze();
    expect(results.violations).toEqual([]);
  });
}
