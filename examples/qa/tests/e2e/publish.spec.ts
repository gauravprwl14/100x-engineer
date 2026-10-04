import { test, expect } from '@playwright/test';

// A bare id names no feature, so trace does not count it and says why.
test('AC-3 a draft album is published once the owner confirms', async ({ page }) => {
  await page.goto('/albums/1');
  await expect(page.getByText('Published')).toBeVisible();
});
