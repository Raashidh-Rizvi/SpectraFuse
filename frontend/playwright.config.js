import {defineConfig} from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  expect: {timeout: 20000},
  use: {channel: process.env.FIRESCOPE_BROWSER || undefined, baseURL: process.env.FIRESCOPE_TEST_URL || 'http://127.0.0.1:8003'},
});
