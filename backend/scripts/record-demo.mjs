import { chromium } from '../../../frontend/node_modules/playwright/index.mjs';
import { mkdir } from 'node:fs/promises';

const output = process.argv[2] || 'data/demo-recording';
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ channel: process.env.FIRESCOPE_BROWSER || 'msedge' });
try {
  const context = await browser.newContext({
    viewport: { width: 1280, height: 900 },
    recordVideo: { dir: output, size: { width: 1280, height: 900 } },
  });
  try {
    const page = await context.newPage();
    await page.goto(process.env.FIRESCOPE_TEST_URL || 'http://127.0.0.1:8003');
    await page.getByRole('heading', { name: 'Burning calendar' }).waitFor({ timeout: 30000 });
    await page.waitForTimeout(2500);
    await page.getByRole('button', { name: /Switch to (light|dark) theme/ }).click();
    await page.waitForTimeout(2200);
    await page.getByRole('combobox', { name: 'Year', exact: true }).selectOption('2022');
    await page.getByRole('button', { name: /Mar 2022/ }).click();
    await page.getByRole('heading', { name: 'Detection map' }).scrollIntoViewIfNeeded();
    await page.waitForTimeout(3000);
    await page.getByRole('checkbox', { name: 'Seasonal anomaly' }).check();
    await page.waitForTimeout(2500);
    await page.getByRole('combobox', { name: 'Region' }).selectOption({label: 'Central Thailand'});
    await page.getByRole('heading', { name: 'Burning calendar' }).waitFor();
    await page.waitForTimeout(3000);
    const video = page.video();
    await context.close();
    await video.saveAs(output + '/firescope-demo.webm');
  } finally {
    await context.close();
  }
} finally {
  await browser.close();
}
