import { clerkSetup } from '@clerk/testing/playwright'
import { test as setup } from '@playwright/test'
import { E2E_BASE_URL } from './utils/e2e-config.js'

setup.describe.configure({ mode: 'serial' })

setup('configure Clerk testing token', async ({ page }) => {
  process.env.CLERK_PUBLISHABLE_KEY ||= process.env.VITE_CLERK_PUBLISHABLE_KEY
  await clerkSetup()
  await page.goto(E2E_BASE_URL)
  await page.waitForFunction(() => window.Clerk?.loaded)
})
