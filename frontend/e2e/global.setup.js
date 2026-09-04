import { clerk, clerkSetup, setupClerkTestingToken } from '@clerk/testing/playwright'
import { test as setup } from '@playwright/test'
import { mkdir } from 'node:fs/promises'
import { join } from 'node:path'

const BASE_URL = process.env.BASE_URL || 'http://localhost:5173'
const STORAGE_DIR = process.env.E2E_STORAGE_DIR || 'test-results/.auth'

async function signInAndSave(page, emailAddress, organizationId, path) {
  await page.goto(BASE_URL)
  await page.waitForFunction(() => window.Clerk?.loaded)
  await setupClerkTestingToken({ page })
  await clerk.signIn({ page, emailAddress })
  if (organizationId) {
    await page.evaluate(async (id) => {
      await window.Clerk.setActive({ organization: id })
    }, organizationId)
    await page.waitForFunction((id) => window.Clerk?.organization?.id === id, organizationId)
  }
  await page.context().storageState({ path })
}

setup.describe.configure({ mode: 'serial' })

setup('configure Clerk testing token and worker auth states', async ({ page, browser }) => {
  await mkdir(STORAGE_DIR, { recursive: true })
  process.env.CLERK_PUBLISHABLE_KEY ||= process.env.VITE_CLERK_PUBLISHABLE_KEY
  await clerkSetup()
  const organizationId = process.env.E2E_CLERK_ORG_ID
  await signInAndSave(
    page,
    process.env.E2E_CLERK_ADMIN_EMAIL,
    organizationId,
    join(STORAGE_DIR, 'admin.json'),
  )

  const teacherContext = await browser.newContext()
  try {
    const teacherPage = await teacherContext.newPage()
    await signInAndSave(
      teacherPage,
      process.env.E2E_CLERK_TEACHER_EMAIL,
      organizationId,
      join(STORAGE_DIR, 'teacher.json'),
    )
  } finally {
    await teacherContext.close()
  }
})
