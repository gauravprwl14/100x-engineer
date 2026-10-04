// No horizontal overflow at the three default widths. 320 CSS px is WCAG 2.2 SC 1.4.10
// Reflow (https://www.w3.org/TR/WCAG22/#reflow); 768 tablet; 1280 desktop.
import { test, expect } from '@playwright/test';

const WIDTHS = [320, 768, 1280];
const ROUTES = ['/', '/<critical route>'];

for (const width of WIDTHS) {
  for (const route of ROUTES) {
    test(`${route} does not scroll horizontally at ${width}px`, { tag: '@responsive' }, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 });
      await page.goto(route);
      const overflow = await page.evaluate(() => {
        const el = document.documentElement;
        return { scrollWidth: el.scrollWidth, clientWidth: el.clientWidth };
      });
      expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth);
    });
  }
}
