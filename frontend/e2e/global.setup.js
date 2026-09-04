import { clerkSetup } from '@clerk/testing/playwright'
import { test as setup } from '@playwright/test'

const BASE_URL = process.env.BASE_URL || 'http://localhost:5173'

setup.describe.configure({ mode: 'serial' })

setup('configure Clerk testing token', async ({ page }) => {
  process.env.CLERK_PUBLISHABLE_KEY ||= process.env.VITE_CLERK_PUBLISHABLE_KEY
  await clerkSetup()
  await page.goto(BASE_URL)
  await page.waitForFunction(() => window.Clerk?.loaded)
})
