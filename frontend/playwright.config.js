import { defineConfig, devices } from '@playwright/test'
import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

function readLocalEnv(relativePath, key) {
  const path = fileURLToPath(new URL(relativePath, import.meta.url))
  if (!existsSync(path)) return undefined
  const line = readFileSync(path, 'utf8').split(/\r?\n/).find((entry) => entry.startsWith(`${key}=`))
  return line?.slice(key.length + 1).trim().replace(/^(["'])(.*)\1$/, '$2')
}

process.env.CLERK_SECRET_KEY ||= readLocalEnv('../backend/.env', 'CLERK_SECRET_KEY')
process.env.VITE_CLERK_PUBLISHABLE_KEY ||= readLocalEnv('.env.local', 'VITE_CLERK_PUBLISHABLE_KEY')
process.env.CLERK_PUBLISHABLE_KEY ||= process.env.VITE_CLERK_PUBLISHABLE_KEY
if (!process.env.CI) {
  process.env.E2E_CLERK_ADMIN_EMAIL ||= 'cronos-ci-admin+clerk_test@example.com'
  process.env.E2E_CLERK_TEACHER_EMAIL ||= 'cronos-ci-teacher+clerk_test@example.com'
}

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
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
      name: 'tutorial',
      testMatch: /e2e[\\/](tutorial[\\/].*|foundation[\\/]tutorial-24steps-navigation)\.spec\.js/,
      use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 720 } },
      dependencies: ['global setup', 'onboarding'],
    },
    {
      name: 'chromium',
      testIgnore: /global\.setup\.js|e2e[\\/]tutorial[\\/]|e2e[\\/]auth[\\/]onboarding-create-organization\.spec\.js|e2e[\\/]foundation[\\/](first-schedule-approval-dashboard|foundation-conflict-recovery|onboarding-foundation-9steps|foundation|tutorial-24steps-navigation)\.spec\.js/,
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
