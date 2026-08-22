import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [['list', { printSteps: true }], ['html', { open: 'never' }]] : 'html',
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
      name: 'onboarding',
      testMatch: /e2e[\\/]auth[\\/]onboarding-create-organization\.spec\.js/,
      use: { ...devices['Desktop Chrome'] },
      dependencies: ['global setup'],
    },
    {
      name: 'foundation setup',
      testMatch: /e2e[\\/]foundation[\\/](first-schedule-approval-dashboard|foundation-conflict-recovery|onboarding-foundation-9steps)\.spec\.js/,
      use: { ...devices['Desktop Chrome'] },
      dependencies: ['global setup', 'onboarding'],
    },
    {
      name: 'foundation activation',
      testMatch: /e2e[\\/]foundation[\\/]foundation\.spec\.js/,
      use: { ...devices['Desktop Chrome'] },
      dependencies: ['foundation setup'],
    },
    {
      name: 'chromium',
      testIgnore: /global\.setup\.js|e2e[\\/]auth[\\/]onboarding-create-organization\.spec\.js|e2e[\\/]foundation[\\/](first-schedule-approval-dashboard|foundation-conflict-recovery|onboarding-foundation-9steps|foundation)\.spec\.js/,
      use: { ...devices['Desktop Chrome'] },
      dependencies: ['foundation activation'],
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
