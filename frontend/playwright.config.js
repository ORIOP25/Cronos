import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'html',
  timeout: 30_000,

  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  projects: [
    {
      name: 'global setup',
      testMatch: /global\.setup\.js/,
    },
    {
      name: 'chromium',
      testIgnore: /global\.setup\.js/,
      use: { ...devices['Desktop Chrome'] },
      dependencies: ['global setup'],
    },
  ],

  webServer: process.env.PLAYWRIGHT_SKIP_WEB_SERVER === '1'
    ? undefined
    : {
        command: 'npm run dev',
        port: 5173,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
})
