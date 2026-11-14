import {defineConfig} from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  use: {baseURL: process.env.FIRESCOPE_TEST_URL || 'http://127.0.0.1:8003'},
});
