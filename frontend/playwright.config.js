import { defineConfig, devices } from '@playwright/test'

process.env.CLERK_PUBLISHABLE_KEY ||= process.env.VITE_CLERK_PUBLISHABLE_KEY
if (!process.env.CI) {
  process.env.E2E_CLERK_ADMIN_EMAIL ||= 'cronos-ci-admin+clerk_test@example.com'
  process.env.E2E_CLERK_TEACHER_EMAIL ||= 'cronos-ci-teacher+clerk_test@example.com'
}

const setupMatch = /global\.setup\.js/
const publicMatch = /e2e[\\/]marketing-public\.spec\.js/
const authMatch = /e2e[\\/]auth[\\/].*\.spec\.js/
const providerMatch = /e2e[\\/]members[\\/]invitations\.spec\.js/
const faultsMatch = /e2e[\\/](?:foundation[\\/]operational-gate-409|tutorial[\\/]tutorial-network-boundary)\.spec\.js/

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: Number(process.env.PLAYWRIGHT_WORKERS || 2),
  reporter: process.env.CI || process.env.PLAYWRIGHT_JUNIT_OUTPUT_FILE
    ? [
        ['list', { printSteps: true }],
        ['junit', { outputFile: process.env.PLAYWRIGHT_JUNIT_OUTPUT_FILE || 'test-results/playwright-junit.xml' }],
        ['html', { open: 'never' }],
      ]
    : 'html',
  timeout: 60_000,
  expect: { timeout: 10_000 },

  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:5174',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },

  projects: [
    {
      name: 'setup',
      testMatch: setupMatch,
      fullyParallel: false,
      workers: 1,
    },
    {
      name: 'public',
      testMatch: publicMatch,
      use: { ...devices['Desktop Chrome'] },
      dependencies: ['setup'],
    },
    {
      name: 'auth',
      testMatch: authMatch,
      use: { ...devices['Desktop Chrome'] },
      dependencies: ['setup'],
    },
    {
      name: 'app',
      testIgnore: [setupMatch, publicMatch, authMatch, providerMatch, faultsMatch],
      use: { ...devices['Desktop Chrome'] },
      // These tests mutate the single disposable E2E organization.
      workers: 1,
      dependencies: ['setup'],
    },
    {
      name: 'provider',
      testMatch: providerMatch,
      use: { ...devices['Desktop Chrome'] },
      workers: 1,
      dependencies: ['setup', 'app'],
    },
    {
      name: 'faults',
      testMatch: faultsMatch,
      use: { ...devices['Desktop Chrome'] },
      workers: 1,
      dependencies: ['setup', 'app', 'provider'],
    },
  ],

})
