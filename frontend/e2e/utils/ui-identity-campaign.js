import { randomBytes } from 'node:crypto'
import { recordCheckpoint } from './acceptance-proof.js'
import { archiveAndRestoreCampaignTeacher, completeFoundation, futureSchoolPeriod, importOriginalData, inviteImportedTeacher, readOriginalExpectations, verifyAcceptedTeacher, verifyImportedData } from '../utils/ui-school.js'
import { addAdminPreference, saveTeacherPreference, verifyAdminAvailability, verifyFutureExecutionAndIncompleteWeek, verifyInitialProgress, verifyPublishedTeacherSchedule, verifyTeacherPreference } from '../utils/ui-teacher.js'
import { exerciseCourseAndInitialClass, exerciseRoomCrud, exerciseSubjectCrud } from '../utils/ui-catalog.js'
import { generateProposal, rejectUnpublishedProposal, verifyFirstProposalAndApprove } from '../utils/ui-generation.js'
import { completeAndResumeGuide } from '../utils/ui-guide.js'
import { restartDisposableSchoolYear } from '../utils/ui-year.js'
import { exerciseSchoolIsolation } from '../utils/ui-isolation.js'
import { exercisePendingOccurrenceAndGap } from '../utils/ui-occurrences.js'
import { awaitAuthStage, awaitClerkLoaded, deliveredCodeReader, evaluateAcrossNavigation, expectIdentity, login, freshSession, withSignUpTestingToken } from '../utils/ui-auth.js'
import { mintClerkTestingToken } from '../../../scripts/cleanup-production-campaign.mjs'
import { campaignSchoolLabel, validateCodeSender } from './acceptance-policy.js'
import { test, expect } from '@playwright/test'

async function rejectOldPassword(page, runtime, testInfo, email, password) {
  await page.goto('/login')
  await awaitClerkLoaded(page)
  await page.getByLabel('Email', { exact: true }).fill(email)
  await page.getByLabel('Palavra-passe', { exact: true }).fill(password)
  let attempted
  const requests = []
  const observe = request => {
    const url = new URL(request.url())
    if (request.method() !== 'POST' || url.origin !== 'https://clerk.cronos.pt'
      || !/^\/v1\/client\/sign_ins(?:\/signin_[a-zA-Z0-9]+\/attempt_first_factor)?$/.test(url.pathname)) return
    let payload
    try { payload = request.postDataJSON() } catch { return }
    if (payload?.strategy !== 'password' || payload.password !== password || (payload.identifier && payload.identifier !== email)) return
    requests.push(request)
    attempted = request
    runtime.allowRequestFailure(request, 422)
  }
  await runtime.action('old-password-rejected', [], async () => {
    page.on('request', observe)
    try {
      const rejected = page.waitForResponse(response => response.request() === attempted)
      await page.getByRole('button', { name: 'Continuar', exact: true }).click()
      const response = await rejected
      expect(response.status()).toBe(422)
      expect(requests).toHaveLength(1)
      const result = await response.json()
      expect(result.errors).toHaveLength(1)
      expect(['form_password_incorrect', 'form_password_or_identifier_incorrect']).toContain(result.errors[0].code)
      const message = page.getByText(/palavra-passe.*incorret/i)
      await expect(message).toBeVisible()
      await expect(page).toHaveURL(/\/login(?:[/?#]|$)/)
      expect(await page.evaluate(() => ({ user: Boolean(window.Clerk.user), session: Boolean(window.Clerk.session) }))).toEqual({ user: false, session: false })
      await expect(page.getByLabel('Email', { exact: true })).toHaveValue(email)
      await testInfo.attach('old-password-rejected', {
        body: Buffer.from(JSON.stringify({ status: response.status(), code: result.errors[0].code,
          path: new URL(response.url()).pathname, visible_message: await message.innerText(), authenticated: false })), contentType: 'application/json',
      })
    } finally { page.off('request', observe) }
  })
}

async function verifyTeacherPermissions(page) {
  const writes = []
  const observe = request => {
    const url = new URL(request.url())
    if (url.pathname.startsWith('/api/v1/') && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method())) writes.push(`${request.method()} ${url.pathname}`)
  }
  page.on('request', observe)
  try {
    for (const route of ['/dashboard', '/members', '/rooms', '/subjects', '/courses', '/config', '/schedules', '/absences', '/timesheets', '/imports', '/foundation', '/guide']) {
      await page.goto(route) // NOSONAR - one page must navigate and assert sequentially
      await expect(page).toHaveURL(/\/my-schedules$/) // NOSONAR - one page must navigate and assert sequentially
      for (const name of ['Nova Sala', 'Novo Curso', 'Adicionar membro', 'Ativar Escola']) await expect(page.getByRole('button', { name, exact: true })).toHaveCount(0) // NOSONAR - one page must navigate and assert sequentially
    }
    expect(writes, 'Denied administrative UI routes cannot issue write requests').toEqual([])
  } finally { page.off('request', observe) }
}

export async function runIdentityCampaign({ page, browser, provenance, deliveredMail, registerSecret, runtime }, testInfo, { persistent = false, persistCredentials, onPrepared } = {}) {
  test.setTimeout(1_200_000)
  if (persistent && (typeof persistCredentials !== 'function' || typeof onPrepared !== 'function')) throw new Error('Persistent preparation requires protected credentials and observed publication evidence')
  const schoolType = persistent ? 'persistent' : 'disposable'
  const runId = process.env.E2E_RUN_ID
  if (!/^[a-z0-9-]+$/.test(runId || '') || !process.env.E2E_RUN_REGISTRY) throw new Error('A signed campaign registry is required before registration')
  const email = `admincronos100+${runId}@gmail.com`
  const password = `Cr!9-${randomBytes(24).toString('base64url')}`
  const recoveredPassword = `Cr!9-${randomBytes(24).toString('base64url')}`
  const teacherEmail = `professorcronos100+${runId}@gmail.com`
  const teacherPassword = `Cr!9-${randomBytes(24).toString('base64url')}`
  await registerSecret(password)
  await registerSecret(recoveredPassword)
  await registerSecret(teacherPassword)
  if (persistent) await persistCredentials({ admin_email: email, teacher_email: teacherEmail,
    admin_registration_password: password, admin_password: recoveredPassword, teacher_password: teacherPassword })
  // Clerk's production sender must be observed/configured, never inferred from development.
  // Clerk sends verification and reset codes from distinct template defaults.
  const sender = validateCodeSender(process.env.E2E_GMAIL_CODE_SENDER)
  const resetSender = validateCodeSender(process.env.E2E_GMAIL_RESET_SENDER)
  const original = await readOriginalExpectations()
  const adminCode = deliveredCodeReader(deliveredMail, 'admin', email)
  const teacherCode = deliveredCodeReader(deliveredMail, 'teacher', teacherEmail)
  const criteria = (after, subject, from = sender) => ({ recipient: email, senders: [from], subject, purpose: 'code', after, before: after + 120_000 })
  // One short-lived vendor token per registration; redacted like any credential.
  const signUpToken = async () => {
    const token = await mintClerkTestingToken({ expectedRevision: process.env.E2E_EXPECTED_REVISION }, process.env)
    await registerSecret(token)
    return token
  }

  const verification = await withSignUpTestingToken(page, await signUpToken(), async () => {
  await page.goto('/register')
  await awaitClerkLoaded(page)
  await page.getByLabel('Nome', { exact: true }).fill('Cronos')
  await page.getByLabel('Apelido', { exact: true }).fill('Aceitação')
  await page.getByLabel('Email', { exact: true }).fill(email)
  await page.getByLabel('Palavra-passe', { exact: true }).fill(password)
  const consent = page.getByRole('checkbox', { name: /poderes para a vincular/ })
  await expect(consent).not.toBeChecked()
  await consent.check()
  // Signed write-ahead intent: the exact founder alias is recorded before the
  // first registration request can create an unverified provider account.
  await provenance.beginActorCreation(email)
  const registrationRequestedAt = Date.now()
  await page.getByRole('button', { name: 'Continuar', exact: true }).click()
  // The founder's delivered-code poll starts only after the real verification
  // UI is visible; a persistent provider challenge fails here, not after 120s.
  await awaitAuthStage(page, { stage: 'code', testInfo })
  const delivered = await deliveredMail('admin', criteria(registrationRequestedAt, /^\d{6} is your verification code$/))
  const codeInput = page.locator('input[autocomplete="one-time-code"]').first()
  await expect(codeInput).toBeVisible()
  await codeInput.pressSequentially(delivered.code)
  await expectIdentity(page, email)
  return delivered
  })
  await provenance.recordCurrentActor()
  // Actual verified session metadata only; never the delivered code or credential.
  const session = await page.evaluate(() => ({
    email_verified: window.Clerk?.user?.primaryEmailAddress?.verification?.status ?? null,
    session_active: Boolean(window.Clerk?.session),
    user_created_at: window.Clerk?.user?.createdAt?.toISOString?.() ?? null,
  }))
  const registration = { registration: true, email_verified: session.email_verified,
    session_active: session.session_active, user_created_at: session.user_created_at, delivered_at: verification.delivered_at }
  await testInfo.attach('registration-verification-observation', {
    body: Buffer.from(JSON.stringify(registration)), contentType: 'application/json',
  })
  await recordCheckpoint(testInfo, ['E2E-01/founder-registration', 'E2E-01/email-verification'], { requires: 'actor', observation: registration })

  await page.goto('/foundation')
  const schoolName = page.locator('input[name="name"]')
  await expect(schoolName).toBeVisible()
  // Clerk initialises this field from its async creation defaults (the instance
  // prefills a default name); filling earlier submits an empty name (422).
  await expect(schoolName).not.toHaveValue('')
  const schoolTitle = `Cronos Aceitação ${campaignSchoolLabel(runId)}`
  await schoolName.fill(schoolTitle)
  await expect(schoolName).toHaveValue(schoolTitle)
  // Signed write-ahead organization intent before Clerk creates the school.
  const organizationIntentId = await provenance.beginOrganizationCreation()
  // A brand-new school has no local member until the app calls /session/bootstrap;
  // its single GET /members/me 403 is that designed signal (403 is never retried).
  // The 403 is allowed only inside this action and only with a successful bootstrap.
  const bootstrapSeen = { forbidden: 0, bootstrapped: 0 }
  const observeBootstrap = response => {
    const url = new URL(response.url())
    if (url.origin !== 'https://api.cronos.pt') return
    if (url.pathname === '/api/v1/members/me' && response.status() === 403) bootstrapSeen.forbidden += 1
    if (url.pathname === '/api/v1/session/bootstrap' && response.request().method() === 'POST' && response.ok()) bootstrapSeen.bootstrapped += 1
  }
  await runtime.action('school-bootstrap', [{ origin: 'https://api.cronos.pt', pathname: '/api/v1/members/me', method: 'GET', status: 403, action: 'school-bootstrap' }], async () => {
    page.on('response', observeBootstrap)
    try {
      await page.getByRole('button', { name: /^(continuar|continue)$/i }).click()
      await expect(page).toHaveURL(/\/foundation$/)
      await expect(page.locator('#school_start_date')).toBeEnabled()
      if (bootstrapSeen.forbidden) expect(bootstrapSeen.bootstrapped, 'A new-school 403 must be followed by a successful bootstrap').toBeGreaterThan(0)
    } finally { page.off('response', observeBootstrap) }
  })
  await provenance.recordCreatedSchool(schoolType, page, organizationIntentId)
  const schoolPeriod = futureSchoolPeriod()
  await completeFoundation(page, schoolPeriod, testInfo)
  await testInfo.attach('foundation-browser-evidence', {
    body: await page.screenshot({ fullPage: true, mask: [page.locator('input, textarea')] }), contentType: 'image/png',
  })
  // End the founder session through the UI before recovery invalidates older sessions.
  await page.getByRole('button', { name: 'Terminar sessão', exact: true }).click()
  await expect.poll(() => evaluateAcrossNavigation(page, () => Boolean(window.Clerk?.loaded && !window.Clerk.user && !window.Clerk.session))).toBe(true)

  await freshSession(browser, testInfo, 'fresh-login', loginPage => login(loginPage, email, password, adminCode))
  await recordCheckpoint(testInfo, ['E2E-02/admin-login-logout', 'E2E-02/new-context-login'], { requires: 'actor' })
  await freshSession(browser, testInfo, 'recovery', async recoveryPage => {
    // A refused code request shows the app's alert; report it instead of a bare timeout.
    const codeStep = recoveryPage.getByRole('heading', { name: 'Introduza o código', exact: true })
    const refusal = recoveryPage.getByRole('alert')
    let recoveryRequestedAt
    for (let attempt = 0; ; attempt += 1) {
      await recoveryPage.goto('/recuperar-palavra-passe')
      await awaitClerkLoaded(recoveryPage)
      await recoveryPage.getByLabel('Email', { exact: true }).fill(email)
      recoveryRequestedAt = Date.now()
      await recoveryPage.getByRole('button', { name: 'Enviar código', exact: true }).click()
      await expect(codeStep.or(refusal).first()).toBeVisible()
      if (await codeStep.isVisible()) break
      const reason = (await refusal.first().innerText()).replaceAll(email, '<email>')
      // Clerk asks a throttled account to wait at least 30 seconds before another code.
      if (attempt === 3 || !/Too many verification code requests/i.test(reason)) throw new Error(`Password recovery refused the code request: ${reason}`)
      await recoveryPage.waitForTimeout(35_000 * 2 ** attempt)
    }
    const recovery = await deliveredMail('admin', criteria(recoveryRequestedAt, /^\d{6} is your reset password code$/, resetSender))
    await recoveryPage.getByLabel('Código de verificação', { exact: true }).fill(recovery.code)
    await recoveryPage.getByRole('button', { name: 'Verificar código', exact: true }).click()
    await recoveryPage.getByLabel('Nova palavra-passe', { exact: true }).fill(recoveredPassword)
    await recoveryPage.getByLabel('Confirmar palavra-passe', { exact: true }).fill(recoveredPassword)
    await recoveryPage.getByRole('button', { name: 'Guardar e entrar', exact: true }).click()
    await expectIdentity(recoveryPage, email)
  })
  await recordCheckpoint(testInfo, 'E2E-03/delivered-recovery', { requires: 'actor' })
  await freshSession(browser, testInfo, 'old-password-rejected', (loginPage, runtime) => rejectOldPassword(loginPage, runtime, testInfo, email, password))
  await recordCheckpoint(testInfo, 'E2E-03/credential-change', { requires: 'actor' })
  await freshSession(browser, testInfo, 'recovered-login', async (loginPage, runtime) => {
    await login(loginPage, email, recoveredPassword, adminCode)
    await recordCheckpoint(testInfo, 'E2E-03/recovered-login', { requires: 'actor', observation: { recovered: true } })
    await importOriginalData(loginPage, testInfo)
    const imported = await verifyImportedData(loginPage, original, testInfo)
    const converted = await inviteImportedTeacher(loginPage, original, imported, teacherEmail, testInfo)
    const invitation = await deliveredMail('teacher', {
      recipient: teacherEmail, senders: ['invitations@cronos.pt'],
      subject: new RegExp(`^Invitation to join Cronos Aceitação ${campaignSchoolLabel(runId)}$`), purpose: 'invitation',
      after: converted.requestedAt, before: converted.requestedAt + 120_000,
      linkHosts: ['clerk.cronos.pt'], linkPath: '/v1/tickets/accept',
    })
    // Bounded, secret-free observation of the actual delivered invitation.
    await testInfo.attach('invitation-delivery-observation', {
      body: Buffer.from(JSON.stringify({ message_id: invitation.id, delivered_at: invitation.delivered_at,
        invited_member_id: converted.member.id, access_status: converted.member.access_status })), contentType: 'application/json',
    })
    // Delivery and the preserved pending-conversion relations share the same UI invitation request.
    await recordCheckpoint(testInfo, ['E2E-04/delivered-invitation', 'E2E-04/pending-conversion-relations'], { requires: 'school' })
    let preferenceSlot
    await freshSession(browser, testInfo, 'teacher-invitation', async teacherPage => {
      await withSignUpTestingToken(teacherPage, await signUpToken(), async () => {
      await teacherPage.goto(invitation.link)
      await expect(teacherPage).toHaveURL(/^https:\/\/cronos\.pt\/(login|register)(?:[/?#]|$)/)
      await awaitClerkLoaded(teacherPage)
      if (new URL(teacherPage.url()).pathname.startsWith('/login')) {
        await teacherPage.getByRole('link', { name: /Registar|Criar conta/ }).click()
      }
      await expect(teacherPage.getByLabel('Palavra-passe', { exact: true })).toBeVisible()
      for (const [label, value] of [['Nome', 'Cronos'], ['Apelido', 'Professor'], ['Email', teacherEmail]]) {
        const field = teacherPage.getByLabel(label, { exact: true })
        if (await field.isVisible() && await field.isEditable()) await field.fill(value) // NOSONAR - one page must navigate and assert sequentially
      }
      await teacherPage.getByLabel('Palavra-passe', { exact: true }).fill(teacherPassword)
      const consent = teacherPage.getByRole('checkbox', { name: /poderes para a vincular/ })
      if (await consent.isVisible()) await consent.check()
      // Signed write-ahead intent before the invited teacher account is created.
      await provenance.beginActorCreation(teacherEmail)
      await teacherPage.getByRole('button', { name: 'Continuar', exact: true }).click()
      // The invited teacher waits for the authenticated session or a persistent
      // provider challenge before the exact-email identity assertion.
      await awaitAuthStage(teacherPage, { stage: 'authenticated', testInfo })
      await expectIdentity(teacherPage, teacherEmail)
      })
      await provenance.recordCurrentActor(teacherPage)
      await teacherPage.goto('/my-schedules')
      await expect(teacherPage).toHaveURL(/\/my-schedules$/)
      preferenceSlot = await saveTeacherPreference(teacherPage, testInfo)
      await expect(teacherPage.getByRole('button', { name: 'Terminar sessão', exact: true })).toBeVisible()
      await teacherPage.getByRole('button', { name: 'Terminar sessão', exact: true }).click()
      await expect.poll(() => evaluateAcrossNavigation(teacherPage, () => Boolean(window.Clerk?.loaded && !window.Clerk.user && !window.Clerk.session))).toBe(true)
    })
    await recordCheckpoint(testInfo, 'E2E-04/invitation-acceptance', { requires: 'school' })
    await freshSession(browser, testInfo, 'teacher-fresh-login', async teacherPage => {
      await login(teacherPage, teacherEmail, teacherPassword, teacherCode)
      await teacherPage.goto('/my-schedules')
      await expect(teacherPage).toHaveURL(/\/my-schedules$/)
      await verifyTeacherPreference(teacherPage, preferenceSlot)
      await verifyTeacherPermissions(teacherPage)
    })
    await recordCheckpoint(testInfo, [
      'E2E-02/teacher-login-logout', 'E2E-15/teacher-admin-routes-denied', 'E2E-15/denied-actions-no-effects',
    ], { requires: 'school', observation: { denied_routes: 13, denied_writes: 0 } })
    await loginPage.reload()
    await verifyAcceptedTeacher(loginPage, converted)
    await verifyAdminAvailability(loginPage, teacherEmail, preferenceSlot)
    await provenance.recordCreatedSchool(schoolType, loginPage)
    await archiveAndRestoreCampaignTeacher(loginPage, converted, testInfo)
    await provenance.recordCreatedSchool(schoolType, loginPage)
    await exerciseRoomCrud(loginPage, runId, testInfo)
    await exerciseSubjectCrud(loginPage, runId, testInfo)
    await exerciseCourseAndInitialClass(loginPage, runId, Number(schoolPeriod.start.slice(0, 4)), testInfo)
    // Aggregate only when all three real CRUD journeys completed.
    await recordCheckpoint(testInfo, 'E2E-06/resource-crud', {
      requires: 'school',
      requiredEvidence: ['room-crud-observation', 'subject-crud-observation', 'course-and-initial-class-observation'],
    })
    await verifyAcceptedTeacher(loginPage, converted)
    const rejected = await generateProposal(loginPage, testInfo, original, imported, { checkpoint: false })
    const rejectionStatus = await rejectUnpublishedProposal(loginPage, testInfo, rejected)
    await addAdminPreference(loginPage, testInfo, converted, preferenceSlot, rejectionStatus)
    const generated = await generateProposal(loginPage, testInfo, original, imported)
    expect(generated.proposal.proposal_id).not.toBe(rejected.proposal.proposal_id)
    expect(generated.versionId).not.toBe(rejected.versionId)
    await verifyFirstProposalAndApprove(loginPage, testInfo, generated, original, imported)
    let operationalHistory
    await freshSession(browser, testInfo, 'teacher-published-schedule-and-progress', async teacherPage => {
      await login(teacherPage, teacherEmail, teacherPassword, teacherCode)
      const { member, week } = await verifyPublishedTeacherSchedule(teacherPage, testInfo, generated, original, imported, converted)
      await verifyFutureExecutionAndIncompleteWeek(teacherPage, testInfo, week)
      await verifyInitialProgress(teacherPage, testInfo, original, imported, member.teacher_id)
      if (persistent) return
      await freshSession(browser, testInfo, 'concurrent-admin-occurrence-decision', async (concurrentPage, concurrentRuntime) => {
        await login(concurrentPage, email, recoveredPassword, adminCode)
        operationalHistory = await exercisePendingOccurrenceAndGap(teacherPage, loginPage, testInfo, week, original, imported.identities, { page: concurrentPage, runtime: concurrentRuntime })
      })
    })
    if (persistent) {
      await onPrepared({ page: loginPage, original, imported, converted, generated, schoolPeriod })
      return
    }
    await completeAndResumeGuide(loginPage, testInfo, runId)
    await restartDisposableSchoolYear(loginPage, testInfo, provenance, converted, imported.snapshot.organization_id, generated, operationalHistory)
    await exerciseSchoolIsolation(loginPage, testInfo, provenance, original, converted, runId)
    const missingPath = '/acceptance-authenticated-missing-path'
    let notFound
    await runtime.action('authenticated-404', [{ origin: 'https://cronos.pt', pathname: missingPath, method: 'GET', status: 404, action: 'authenticated-404' }], async () => {
      const response = await loginPage.goto(missingPath)
      expect(response.status()).toBe(404)
      const heading = loginPage.getByRole('heading', { name: 'Página não encontrada', exact: true })
      await expect(heading).toBeVisible()
      notFound = { status: response.status(), heading: await heading.innerText(), url: loginPage.url() }
    })
    await testInfo.attach('authenticated-404-observation', { body: Buffer.from(JSON.stringify(notFound)), contentType: 'application/json' })
    await recordCheckpoint(testInfo, 'E2E-16/authenticated-404', { requires: 'school', observation: notFound })
    await loginPage.getByRole('link', { name: 'Ir para o painel', exact: true }).click()
    await expect(loginPage).toHaveURL(/\/dashboard$/)
    await loginPage.getByRole('button', { name: 'Terminar sessão', exact: true }).click()
    await expect.poll(() => evaluateAcrossNavigation(loginPage, () => Boolean(window.Clerk?.loaded && !window.Clerk.user && !window.Clerk.session))).toBe(true)
    await loginPage.goto('/dashboard')
    await expect(loginPage).toHaveURL(/\/login(?:[/?#]|$)/)
    await expect(loginPage.getByLabel('Email', { exact: true })).toBeVisible()
  })
}
