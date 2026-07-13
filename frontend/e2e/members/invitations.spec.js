import { test, expect } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectNoAppCrash,
  goTo,
  loginAsAdminReal,
} from '../utils/clerk-helpers.js'

function requiredTestEmail(name) {
  const value = process.env[name]
  if (!value?.toLowerCase().endsWith('+clerk_test@example.com')) {
    throw new Error(`${name} must be a Clerk reserved test email.`)
  }
  return value
}

async function openMemberForm(page) {
  await page.getByRole('button', { name: 'Adicionar membro' }).click()
  await expect(page.getByRole('heading', { name: 'Adicionar membro' })).toBeVisible()
}

async function fillTeacher(page, { name, email, access }) {
  await page.getByLabel('Nome').fill(name)
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Tipo de membro').selectOption('teacher')
  await page.getByLabel('Acesso do professor').selectOption(access)
}

async function saveAndExpect(page, expectedStatus) {
  const responsePromise = page.waitForResponse((response) => (
    response.url().includes('/api/v1/members')
      && ['POST', 'PATCH'].includes(response.request().method())
  ))
  await page.getByRole('button', { name: 'Guardar' }).click()
  const response = await responsePromise
  expect(response.status()).toBe(expectedStatus)
  await expect(page.getByRole('heading', { name: /Adicionar membro|Editar membro/ })).toHaveCount(0)
  await expectNoAppCrash(page)
}

test.describe.serial('Member invitations — real Clerk', () => {
  test.beforeEach(async ({ page }) => {
    attachRuntimeGuards(page)
    await loginAsAdminReal(page)
    await goTo(page, '/members')
  })

  test('creates a platform teacher with Clerk millisecond expiry', async ({ page }) => {
    const email = requiredTestEmail('E2E_CLERK_INVITE_CREATE_EMAIL')
    await openMemberForm(page)
    await fillTeacher(page, {
      name: 'E2E Platform Teacher',
      email,
      access: 'platform',
    })
    await saveAndExpect(page, 201)

    const row = page.getByRole('row').filter({ hasText: email })
    await expect(row).toContainText('Convite pendente')
  })

  test('converts a scheduler-only teacher to platform access', async ({ page }) => {
    const email = requiredTestEmail('E2E_CLERK_INVITE_CONVERT_EMAIL')
    await openMemberForm(page)
    await fillTeacher(page, {
      name: 'E2E Converted Teacher',
      email,
      access: 'scheduler_only',
    })
    await saveAndExpect(page, 201)

    const row = page.getByRole('row').filter({ hasText: email })
    await expect(row).toContainText('Sem acesso')
    await row.getByRole('button', { name: 'Editar membro' }).click()
    await expect(page.getByRole('heading', { name: 'Editar membro' })).toBeVisible()
    await page.getByLabel('Acesso do professor').selectOption('platform')
    await saveAndExpect(page, 200)
    await expect(row).toContainText('Convite pendente')
  })
})
