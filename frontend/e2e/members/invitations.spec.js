import { createClerkClient } from '@clerk/backend'
import { setupClerkTestingToken } from '@clerk/testing/playwright'
import { test, expect } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectNoAppCrash,
  goTo,
  loginAsAdminReal,
  expectRouteReady,
} from '../utils/clerk-helpers.js'
import { createE2eRunKey, E2E_BASE_URL } from '../utils/e2e-config.js'

let createdInvitation

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
  const body = await response.json()
  await expect(page.getByRole('heading', { name: /Adicionar membro|Editar membro/ })).toHaveCount(0)
  await expectNoAppCrash(page)
  return body
}

async function completeVisibleInvitationAuth(page, email) {
  await expect(page).toHaveURL(/\/(?:login|register)(?:[/?#].*)?$/, { timeout: 30_000 })
  const emailInput = page.locator('input[type="email"]:visible').first()
  if (await emailInput.isVisible().catch(() => false)) {
    await emailInput.fill(email)
    await expect(emailInput).toHaveValue(email)
    await page.getByRole('button', { name: /continuar|continue|entrar|criar conta/i }).last().click()
  }

  for (let attempt = 0; attempt < 6; attempt += 1) {
    const codeInput = page.locator('input[name="code"]')
    if (await codeInput.isVisible().catch(() => false)) {
      await codeInput.fill('424242')
      await page.getByRole('button', { name: /continuar|continue|verificar|confirmar/i }).last().click()
    }
    const firstName = page.locator('input[name="firstName"]')
    if (await firstName.isVisible().catch(() => false)) await firstName.fill('Cronos')
    const lastName = page.locator('input[name="lastName"]')
    if (await lastName.isVisible().catch(() => false)) await lastName.fill('Professor')
    const password = page.locator('input[name="password"]')
    if (await password.isVisible().catch(() => false)) await password.fill('Cronos-E2E-Password-123!')
    const consent = page.getByRole('checkbox').first()
    if (await consent.isVisible().catch(() => false) && !(await consent.isChecked())) await consent.check()
    if (/\/(?:foundation|dashboard|my-schedules)(?:[/?#]|$)/.test(page.url())) return
    const continueButton = page.getByRole('button', { name: /continuar|continue|verificar|confirmar|entrar|criar conta/i }).last()
    if (await continueButton.isVisible().catch(() => false)) await continueButton.click()
    await page.waitForTimeout(1000)
  }
  await expect(page).toHaveURL(/\/(?:foundation|dashboard|my-schedules)(?:[/?#]|$)/, { timeout: 30_000 })
}

async function recoverInvitationPassword(page, email) {
  await page.goto(`${E2E_BASE_URL}/recuperar-palavra-passe`, { waitUntil: 'domcontentloaded' })
  await page.locator('#recovery-email').fill(email)
  await page.getByRole('button', { name: /enviar código/i }).click()
  await expect(page.getByRole('heading', { name: /introduza o código/i })).toBeVisible({ timeout: 30_000 })
  await page.locator('#recovery-code').fill('424242')
  await page.getByRole('button', { name: /verificar código/i }).click()
  await expect(page.getByRole('heading', { name: /escolha uma nova palavra-passe/i })).toBeVisible({ timeout: 30_000 })
  await page.locator('#recovery-password').fill('Cronos-E2E-Password-123!')
  await page.locator('#recovery-confirm-password').fill('Cronos-E2E-Password-123!')
  await page.getByRole('button', { name: /guardar e entrar/i }).click()
  await expect(page).not.toHaveURL(/\/recuperar-palavra-passe$/, { timeout: 30_000 })
}

test.describe.serial('Member invitations — real Clerk', () => {
  test.describe.configure({ retries: 0 })

  test.beforeEach(async ({ page }) => {
    attachRuntimeGuards(page)
    await loginAsAdminReal(page)
    await goTo(page, '/members')
  })

  test('creates a platform teacher with Clerk millisecond expiry', async ({ page }) => {
    const email = `cronos-invite-${createE2eRunKey()}+clerk_test@example.com`
    await openMemberForm(page)
    await fillTeacher(page, {
      name: 'E2E Platform Teacher',
      email,
      access: 'platform',
    })
    createdInvitation = { ...await saveAndExpect(page, 201), email }
    expect(createdInvitation.clerk_invitation_id).toMatch(/^orginv_/)

    const row = page.getByRole('row').filter({ hasText: email })
    await expect(row).toContainText('Convite pendente')
    await expect(row).toContainText('Convite enviado; aguarda aceitação.')
  })

  test('accepts the invitation through the visible Clerk flow and auto-activates the unique organization', async ({ browser, page }) => {
    test.setTimeout(180_000)
    const email = createdInvitation.email
    const secretKey = process.env.CLERK_SECRET_KEY
    if (!secretKey) throw new Error('CLERK_SECRET_KEY is required for invitation E2E.')
    if (!createdInvitation?.clerk_invitation_id) throw new Error('The invitation creation response was not captured.')

    const configuredOrganizationId = process.env.E2E_CLERK_ORG_ID
    if (!configuredOrganizationId) {
      await page.waitForFunction(
        () => Boolean(window.Clerk?.organization?.id),
        null,
        { timeout: 30_000 },
      )
    }
    await page.waitForFunction(
      () => Boolean(window.Clerk?.user?.id),
      null,
      { timeout: 30_000 },
    )
    const { adminUserId } = await page.evaluate(() => ({
      adminUserId: window.Clerk?.user?.id,
    }))
    const organizationId = configuredOrganizationId || await page.evaluate(
      () => window.Clerk?.organization?.id,
    )
    if (!organizationId || !adminUserId) {
      throw new Error('The authenticated Clerk organization and admin user are required.')
    }
    const client = createClerkClient({ secretKey })
    const invitation = await client.organizations.getOrganizationInvitation({
      organizationId,
      invitationId: createdInvitation.clerk_invitation_id,
    })
    expect(invitation.url).toBeTruthy()

    const inviteContext = await browser.newContext({ storageState: { cookies: [], origins: [] } })
    const invitePage = await inviteContext.newPage()
    try {
      attachRuntimeGuards(invitePage)
      await setupClerkTestingToken({ page: invitePage })
      await invitePage.goto(invitation.url, { waitUntil: 'domcontentloaded' })
      await completeVisibleInvitationAuth(invitePage, email)
      await invitePage.waitForFunction((id) => window.Clerk?.organization?.id === id, organizationId)
      await expect.poll(
        () => invitePage.evaluate(async () => {
          const token = await window.Clerk.session.getToken()
          const response = await fetch('/api/v1/members/me', { headers: { Authorization: `Bearer ${token}` } })
          return response.ok ? (await response.json()).capabilities : null
        }),
        { timeout: 60_000 },
      ).toContain('teacher')
      await invitePage.goto(`${E2E_BASE_URL}/my-schedules`, { waitUntil: 'domcontentloaded' })
      await expectRouteReady(invitePage, '/my-schedules')

      await invitePage.evaluate(() => window.Clerk.signOut())
      await recoverInvitationPassword(invitePage, email)
      await invitePage.evaluate(() => window.Clerk.signOut())
      await invitePage.goto(`${E2E_BASE_URL}/login`, { waitUntil: 'domcontentloaded' })
      await completeVisibleInvitationAuth(invitePage, email)
      await invitePage.waitForFunction((id) => window.Clerk?.organization?.id === id, organizationId)
      await invitePage.goto(`${E2E_BASE_URL}/my-schedules`, { waitUntil: 'domcontentloaded' })
      await expectRouteReady(invitePage, '/my-schedules')
    } finally {
      await inviteContext.close()
      const users = await client.users.getUserList({ emailAddress: [email] })
      for (const user of users.data ?? []) {
        const memberships = await client.organizations.getOrganizationMembershipList({
          organizationId,
          userId: [user.id],
        })
        for (const membership of memberships.data ?? []) {
          await client.organizations.deleteOrganizationMembership({
            organizationId,
            userId: membership.publicUserData?.userId || user.id,
            requestingUserId: adminUserId,
          })
        }
        await client.users.deleteUser(user.id)
      }
      const currentInvitation = await client.organizations.getOrganizationInvitation({
        organizationId,
        invitationId: createdInvitation.clerk_invitation_id,
      })
      if (currentInvitation.status === 'pending') {
        await client.organizations.revokeOrganizationInvitation({
          organizationId,
          invitationId: createdInvitation.clerk_invitation_id,
          requestingUserId: adminUserId,
        })
      }
    }
  })

  test('links an already existing Clerk user to the organization and verifies teacher access', async ({ browser, page }) => {
    test.setTimeout(120_000)
    const secretKey = process.env.CLERK_SECRET_KEY
    if (!secretKey) throw new Error('CLERK_SECRET_KEY is required for invitation E2E.')
    const email = `cronos-existing-${createE2eRunKey()}+clerk_test@example.com`
    const client = createClerkClient({ secretKey })
    const user = await client.users.createUser({
      emailAddress: [email],
      firstName: 'Cronos',
      lastName: 'Existing',
      skipPasswordRequirement: true,
      legalAcceptedAt: new Date(),
    })
    const organizationId = await page.evaluate(() => window.Clerk.organization.id)
    const adminUserId = await page.evaluate(() => window.Clerk.user.id)
    try {
      await openMemberForm(page)
      await fillTeacher(page, { name: 'E2E Existing Teacher', email, access: 'platform' })
      const member = await saveAndExpect(page, 201)
      expect(member.access_status).toBe('active')
      expect(member.clerk_membership_id).toBeTruthy()

      const context = await browser.newContext({ storageState: { cookies: [], origins: [] } })
      const invitedPage = await context.newPage()
      try {
        attachRuntimeGuards(invitedPage)
        const ticket = await client.signInTokens.createSignInToken({ userId: user.id, expiresInSeconds: 300 })
        const ticketUrl = new URL(ticket.url)
        ticketUrl.searchParams.set('redirect_url', new URL('/my-schedules', E2E_BASE_URL).toString())
        await setupClerkTestingToken({ page: invitedPage })
        await invitedPage.goto(ticketUrl.toString(), { waitUntil: 'domcontentloaded' })
        await expect(invitedPage).toHaveURL(/\/my-schedules(?:[/?#].*)?$/, { timeout: 30_000 })
        await invitedPage.waitForFunction((id) => window.Clerk?.organization?.id === id, organizationId)
        await expectRouteReady(invitedPage, '/my-schedules')
      } finally {
        await context.close()
      }
    } finally {
      const memberships = await client.organizations.getOrganizationMembershipList({
        organizationId,
        userId: [user.id],
      })
      for (const membership of memberships.data ?? []) {
        await client.organizations.deleteOrganizationMembership({
          organizationId,
          userId: membership.publicUserData?.userId || user.id,
          requestingUserId: adminUserId,
        })
      }
      await client.users.deleteUser(user.id)
    }
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
    await expect(row).toContainText('Convite enviado; aguarda aceitação.')
  })
})
