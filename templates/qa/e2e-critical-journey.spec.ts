// Critical-journey e2e: one test per journey that must never break, each tagged with the
// acceptance criteria it proves so `100x testplan trace <spec> --tests e2e` can count it.
// Keep this list short (sign-in, the money/primary path, the one destructive action) —
// everything else belongs lower in the pyramid. API: https://playwright.dev/docs/test-annotations
import { test, expect } from '@playwright/test';

// Journey: <name the journey>
test('AC-1 <the outcome the AC states, as a sentence>', { tag: ['@critical', '@AC-1'] }, async ({ page }) => {
  await page.goto('/');
  await page.getByRole('link', { name: '<entry point>' }).click();
  await page.getByLabel('<field label>').fill('<valid value>');
  await page.getByRole('button', { name: '<submit>' }).click();
  await expect(page.getByRole('status')).toHaveText('<success message from the spec>');
});

test('AC-2 <the rejection the AC states>', { tag: ['@critical', '@AC-2'] }, async ({ page }) => {
  await page.goto('/<protected route>');
  await expect(page).toHaveURL(/sign_in|login/);
});
