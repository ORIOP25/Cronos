import { test as setup } from '@playwright/test'
import { mkdir } from 'node:fs/promises'
import { dirname } from 'node:path'
import { loginAsAdminReal } from './utils/clerk-helpers.js'

const adminAuthState = '.auth/admin.json'

setup('save administrator session for application tests', async ({ page }) => {
  await loginAsAdminReal(page)
  await page.waitForFunction(
    (organizationId) => Boolean(window.Clerk?.session && window.Clerk?.organization?.id)
      && (!organizationId || window.Clerk.organization.id === organizationId),
    process.env.E2E_CLERK_ORG_ID,
  )
  await mkdir(dirname(adminAuthState), { recursive: true })
  await page.context().storageState({ path: adminAuthState })
})
