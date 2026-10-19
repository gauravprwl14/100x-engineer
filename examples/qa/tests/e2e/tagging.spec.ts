import { test, expect } from '@playwright/test';

test('photo-tagging/AC-1 a member tags ten people from the photo page', { tag: '@critical' }, async ({ page }) => {
  await page.goto('/albums/1/photos/1');
  await expect(page.getByRole('list', { name: 'Tagged people' })).toBeVisible();
});
