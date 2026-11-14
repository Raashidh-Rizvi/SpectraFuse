import {expect, test} from '@playwright/test';

test('themes persist and calendar fits a phone', async ({page}) => {
  await page.setViewportSize({width:390,height:844});
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'Burning calendar'})).toBeVisible();
  const button = page.getByRole('button',{name:/Switch to (light|dark) theme/});
  const before = await button.getAttribute('aria-label');
  await button.click();
  await expect(button).not.toHaveAttribute('aria-label',before);
  const after = await button.getAttribute('aria-label');
  await page.reload();
  await expect(button).toHaveAttribute('aria-label',after);
  await page.locator('.filters select').nth(2).selectOption('2022');
  await page.getByRole('button',{name:/Mar 2022/}).click();
  await expect(page.locator('.geo p')).toContainText('2022-03');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test('polygon restricts the monthly hotspots', async ({request}) => {
  const response = await request.get('/api/fire/monthly-hotspots',{
    params:{month:'2022-03',polygon:'0,0;1,0;1,1'}
  });
  expect(response.ok()).toBeTruthy();
  expect((await response.json()).total).toBe(0);
});

test('mobile hotspot colors follow the selected sensor', async ({page}) => {
  await page.setViewportSize({width:390,height:844});
  await page.goto('/');
  await page.getByRole('combobox',{name:'Year',exact:true}).selectOption('2022');
  await page.getByRole('button',{name:/Mar 2022/}).click();
  const sensor = page.getByRole('combobox',{name:'Map product'});
  const map = page.locator('.geo .leaflet-overlay-pane');
  for (const [source, color, label] of [
    ['MODIS_SP','#e52e3e','MODIS'],
    ['VIIRS_SNPP_SP','#ff861f','VIIRS S-NPP'],
    ['VIIRS_NOAA20_SP','#de3476','VIIRS NOAA-20'],
  ]) {
    await sensor.selectOption(source);
    await expect(page.locator('.sensor-legend [data-active=true]')).toContainText(label);
    await expect(map.locator('path[fill="'+color+'"]').first()).toBeAttached();
  }
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});
