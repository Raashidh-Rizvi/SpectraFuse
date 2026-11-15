import { expect, test } from '@playwright/test';

test.describe('SpectraFuse AI Assistant Drawer (Phase 5)', () => {
  test('TC-U01: Toggle open and close chat panel via header button, floating button, and Esc key', async ({ page }) => {
    await page.goto('/');

    const panel = page.locator('.chat-drawer-panel');
    await expect(panel).not.toHaveClass(/open/);

    // Open via Header AI Assistant button
    const headerBtn = page.getByRole('button', { name: 'Open AI Assistant' });
    await expect(headerBtn).toBeVisible();
    await headerBtn.click();

    await expect(panel).toHaveClass(/open/);
    await expect(page.getByRole('dialog', { name: 'Active Fire AI Assistant' })).toBeVisible();

    // Close via Esc key
    await page.keyboard.press('Escape');
    await expect(panel).not.toHaveClass(/open/);

    // Open via Floating action button
    const floatingBtn = page.getByRole('button', { name: 'Open Satellite Fire AI Assistant' });
    await expect(floatingBtn).toBeVisible();
    await floatingBtn.click();
    await expect(panel).toHaveClass(/open/);

    // Close via close icon button (X)
    const closeBtn = page.getByRole('button', { name: 'Close assistant' });
    await closeBtn.click();
    await expect(panel).not.toHaveClass(/open/);
  });

  test('TC-U02 & TC-U03: Chat message renders provenance badges and mock responses', async ({ page }) => {
    // Intercept chat API with a structured mock assistant message
    await page.route('**/api/fire/chat', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          answer: 'In August 2021, Sri Lanka had **1,240** fire detections observed by VIIRS.',
          intent: 'monthly_summary',
          evidence: [
            {
              metric: 'monthly_detections',
              value: 1240,
              product: 'VIIRS_SNPP_SP',
              status: 'observed',
              coverage: 'complete',
              calibration_applied: false,
              spatial_resolution: '375m',
              temporal_window: '2021-08',
            },
          ],
          calculations: [
            {
              step_name: 'Raw Count Aggregation',
              formula: 'sum(daily_counts)',
              inputs: { month: '2021-08' },
              result: 1240,
              notes: 'Complete monthly partition',
            },
          ],
          limitations: ['Detections count thermal anomalies, not burned area or individual wildfires.'],
          ui_actions: [
            {
              type: 'show_on_map',
              payload: {
                region: 'sri-lanka',
                start: '2021-08-01',
                end: '2021-08-31',
                bbox: '79.5,5.8,82,10',
                layers: ['VIIRS_SNPP_SP', 'harmonized'],
              },
            },
          ],
          downloads: [
            {
              label: 'Download August 2021 CSV',
              url: '/api/fire/download?region=sri-lanka&year=2021',
              format: 'csv',
            },
          ],
          region: 'sri-lanka',
          period: '2021-08',
        }),
      });
    });

    await page.goto('/');

    // Open chat drawer
    await page.getByRole('button', { name: 'Open AI Assistant' }).click();

    // Type query and submit
    const textarea = page.getByLabel('Chat query input');
    await textarea.fill('What was the fire activity in August 2021?');
    await page.getByRole('button', { name: 'Send' }).click();

    // Verify user message is displayed
    await expect(page.locator('.user-bubble')).toContainText('What was the fire activity in August 2021?');

    // Verify assistant answer
    await expect(page.locator('.assistant-bubble')).toContainText('In August 2021, Sri Lanka had 1,240 fire detections');

    // Verify TC-U02: Provenance badge "Observed by VIIRS"
    const badge = page.locator('.provenance-badge.badge-observed');
    await expect(badge).toBeVisible();
    await expect(badge).toContainText('Observed by VIIRS');

    // Verify TC-U04: Calculation Accordion
    const accordionSummary = page.locator('.calculation-breakdown summary');
    await expect(accordionSummary).toBeVisible();
    await accordionSummary.click();
    await expect(page.locator('.calc-formula-block code')).toContainText('sum(daily_counts)');

    // Verify TC-U05: Interactive Map Action button closes drawer and focuses map
    const mapActionBtn = page.getByRole('button', { name: /Show On Map/i });
    await expect(mapActionBtn).toBeVisible();
    await mapActionBtn.click();
    await expect(page.locator('.chat-drawer-panel')).not.toHaveClass(/open/);

    // Verify TC-U06: Download CSV link
    const downloadLink = page.getByRole('link', { name: /Download August 2021 CSV/i });
    await expect(downloadLink).toBeVisible();
    await expect(downloadLink).toHaveAttribute('href', '/api/fire/download?region=sri-lanka&year=2021');
  });

  test('TC-U07: Markdown safety strips malicious script tags', async ({ page }) => {
    let alertTriggered = false;
    page.on('dialog', async (dialog) => {
      alertTriggered = true;
      await dialog.dismiss();
    });

    await page.route('**/api/fire/chat', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          answer: 'Safe response <script>alert("xss")</script> without script execution.',
          intent: 'general',
          evidence: [],
          calculations: [],
          limitations: [],
          ui_actions: [],
          downloads: [],
        }),
      });
    });

    await page.goto('/');
    await page.getByRole('button', { name: 'Open AI Assistant' }).click();
    await page.getByLabel('Chat query input').fill('Test script tags');
    await page.getByRole('button', { name: 'Send' }).click();

    await expect(page.locator('.assistant-bubble')).toContainText('Safe response without script execution.');
    expect(alertTriggered).toBe(false);
  });

  test('TC-U08: Chat panel adapts seamlessly across light and dark themes', async ({ page }) => {
    await page.goto('/');

    // Toggle theme to dark/light first
    const themeBtn = page.getByRole('button', { name: /Switch to (light|dark) theme/ });
    await themeBtn.click();

    // Open chat drawer
    await page.getByRole('button', { name: 'Open AI Assistant' }).click();

    const panel = page.locator('.chat-drawer-panel');
    await expect(panel).toBeVisible();
    await expect(page.getByLabel('Chat query input')).toBeVisible();
  });
});
