import { resolve } from 'node:path'
import { defineConfig, devices } from '@playwright/test'
import { E2E_BASE_URL } from './e2e/utils/e2e-config.js'

process.env.CLERK_PUBLISHABLE_KEY ||= process.env.VITE_CLERK_PUBLISHABLE_KEY
if (!process.env.CI) {
  process.env.E2E_CLERK_ADMIN_EMAIL ||= 'cronos-ci-admin+clerk_test@example.com'
  process.env.E2E_CLERK_TEACHER_EMAIL ||= 'cronos-ci-teacher+clerk_test@example.com'
}

const setupMatch = /global\.setup\.js/
const authStateMatch = /auth\.state\.setup\.js/
const publicMatch = /e2e[\\/]marketing-public\.spec\.js/
const authMatch = /e2e[\\/]auth[\\/].*\.spec\.js/
const providerMatch = /e2e[\\/]members[\\/]invitations\.spec\.js/
// Fresh-organization journeys: each spec creates and deletes its own Clerk
// organization, so it never touches the single shared E2E organization and is
// independent of the serialized shared-organization chain.
const isolatedMatch = /e2e[\\/]foundation[\\/](?:foundation|foundation-24h-time|foundation-conflict-recovery|internship-flow|onboarding-foundation-10steps|first-schedule-approval-dashboard|operational-gate-409)\.spec\.js/
// Tutorial/localStorage-only journeys: no business writes; they assert only on
// per-context storage, so they never race the shared-organization chain.
const readonlyMatch = /e2e[\\/](?:tutorial[\\/](?:tutorial-local|tutorial-network-boundary)|foundation[\\/]tutorial-13steps-navigation)\.spec\.js/
const capacityMatch = /e2e[\\/]capacity[\\/]capacity\.spec\.js/
const outputDirectory = resolve(process.env.PLAYWRIGHT_OUTPUT_DIR || 'test-results')
const reporter = process.env.CI || process.env.PLAYWRIGHT_JUNIT_OUTPUT_FILE
  ? [
      ['list', { printSteps: true }],
      ['junit', { outputFile: process.env.PLAYWRIGHT_JUNIT_OUTPUT_FILE || 'test-results/playwright-junit.xml' }],
      ['html', { open: 'never' }],
    ]
  : 'html'

export default defineConfig({
  testDir: './e2e',
  outputDir: outputDirectory,
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: Number(process.env.PLAYWRIGHT_WORKERS || 2),
  reporter,
  timeout: 60_000,
  expect: { timeout: 10_000 },

  use: {
    baseURL: E2E_BASE_URL,
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
      // The public marketing routes are readonly and hit no Clerk API, so this
      // project keeps the real browser without the global Clerk testing-token
      // setup. It must not depend on signed-in state or `setup`.
      name: 'public',
      testMatch: publicMatch,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'auth-state',
      testMatch: authStateMatch,
      fullyParallel: false,
      workers: 1,
      dependencies: ['setup'],
    },
    {
      name: 'auth',
      testMatch: authMatch,
      use: { ...devices['Desktop Chrome'] },
      // Bound genuine Clerk sign-ins to the existing concurrency.
      workers: 2,
      dependencies: ['setup'],
    },
    {
      // Fresh Clerk organizations owned by each spec. These never read or
      // write the shared organization, so they run in parallel with the
      // shared-organization chain instead of behind it.
      name: 'isolated',
      testMatch: isolatedMatch,
      use: { ...devices['Desktop Chrome'] },
      workers: 1,
      dependencies: ['setup'],
    },
    {
      // Tutorial/localStorage journeys. The saved admin session is enough and
      // the cases assert only per-context storage, but the app shell reads
      // shared-organization state, and the mutating chain soft-resets the
      // school year (`/school/settings/soft-reset`). Serialize after the whole
      // mutating chain instead of racing it.
      name: 'readonly',
      testMatch: readonlyMatch,
      use: { ...devices['Desktop Chrome'] },
      workers: 1,
      dependencies: ['provider'],
    },
    {
      name: 'app',
      testIgnore: [setupMatch, authStateMatch, publicMatch, authMatch, providerMatch, isolatedMatch, readonlyMatch, capacityMatch],
      use: { ...devices['Desktop Chrome'] },
      // These tests mutate the single disposable E2E organization.
      workers: 1,
      dependencies: ['auth-state'],
    },
    {
      name: 'provider',
      testMatch: providerMatch,
      use: { ...devices['Desktop Chrome'] },
      workers: 1,
      dependencies: ['app'],
    },
    ...(process.env.CAPACITY_ENABLED === '1' ? [{
      name: 'capacity',
      testMatch: capacityMatch,
      use: { ...devices['Desktop Chrome'] },
      workers: 1,
      dependencies: ['setup'],
    }] : []),
  ],

})
