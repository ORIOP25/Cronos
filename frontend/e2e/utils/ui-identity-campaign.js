import { randomBytes } from 'node:crypto'
import { archiveAndRestoreCampaignTeacher, completeFoundation, futureSchoolPeriod, importOriginalData, inviteImportedTeacher, readOriginalExpectations, verifyAcceptedTeacher, verifyImportedData } from '../utils/ui-school.js'
import { addAdminPreference, saveTeacherPreference, verifyAdminAvailability, verifyFutureExecutionAndIncompleteWeek, verifyInitialProgress, verifyPublishedTeacherSchedule, verifyTeacherPreference } from '../utils/ui-teacher.js'
import { exerciseCourseAndInitialClass, exerciseRoomCrud, exerciseSubjectCrud } from '../utils/ui-catalog.js'
import { generateProposal, rejectUnpublishedProposal, verifyFirstProposalAndApprove } from '../utils/ui-generation.js'
import { completeAndResumeGuide } from '../utils/ui-guide.js'
import { restartDisposableSchoolYear } from '../utils/ui-year.js'
import { exerciseSchoolIsolation } from '../utils/ui-isolation.js'
import { exercisePendingOccurrenceAndGap } from '../utils/ui-occurrences.js'
import { expectIdentity, login, freshSession } from '../utils/ui-auth.js'
import { test, expect } from '@playwright/test'

async function rejectOldPassword(page, runtime, testInfo, email, password) {
  await page.goto('/login')
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
      await page.goto(route)
      await expect(page).toHaveURL(/\/my-schedules$/)
      for (const name of ['Nova Sala', 'Novo Curso', 'Adicionar membro', 'Ativar Escola']) await expect(page.getByRole('button', { name, exact: true })).toHaveCount(0)
    }
    expect(writes, 'Denied administrative UI routes cannot issue write requests').toEqual([])
  } finally { page.off('request', observe) }
}

export async function runIdentityCampaign({ page, browser, provenance, deliveredMail, registerSecret }, testInfo, { persistent = false, persistCredentials, onPrepared } = {}) {
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
  const sender = process.env.E2E_GMAIL_CODE_SENDER
  if (!/^[a-z0-9._-]+@cronos\.pt$/.test(sender || '')) throw new Error('Configure the observed production code sender')
  const original = await readOriginalExpectations()
  const criteria = (after, subject) => ({ recipient: email, senders: [sender], subject, purpose: 'code', after, before: after + 120_000 })

  await page.goto('/register')
  await page.getByLabel('Nome', { exact: true }).fill('Cronos')
  await page.getByLabel('Apelido', { exact: true }).fill('Aceitação')
  await page.getByLabel('Email', { exact: true }).fill(email)
  await page.getByLabel('Palavra-passe', { exact: true }).fill(password)
  const consent = page.getByRole('checkbox', { name: /poderes para a vincular/ })
  await expect(consent).not.toBeChecked()
  await consent.check()
  const registrationRequestedAt = Date.now()
  await page.getByRole('button', { name: 'Continuar', exact: true }).click()
  const verification = await deliveredMail('admin', criteria(registrationRequestedAt, /^\d{6} is your verification code$/))
  const codeInput = page.locator('input[autocomplete="one-time-code"]').first()
  await expect(codeInput).toBeVisible()
  await codeInput.pressSequentially(verification.code)
  await expectIdentity(page, email)
  await provenance.recordCurrentActor()

  await page.goto('/foundation')
  const schoolName = page.locator('input[name="name"]')
  await expect(schoolName).toBeVisible()
  await schoolName.fill(`Cronos Aceitação ${runId}`)
  await page.getByRole('button', { name: /^(continuar|continue)$/i }).click()
  await expect(page).toHaveURL(/\/foundation$/)
  await expect(page.locator('#school_start_date')).toBeEnabled()
  await provenance.recordCreatedSchool(schoolType)
  const schoolPeriod = futureSchoolPeriod()
  await completeFoundation(page, schoolPeriod)
  await testInfo.attach('foundation-browser-evidence', {
    body: await page.screenshot({ fullPage: true, mask: [page.locator('input, textarea')] }), contentType: 'image/png',
  })
  // End the founder session through the UI before recovery invalidates older sessions.
  await page.getByRole('button', { name: 'Terminar sessão', exact: true }).click()
  await expect.poll(() => page.evaluate(() => Boolean(window.Clerk?.loaded && !window.Clerk.user && !window.Clerk.session))).toBe(true)

  await freshSession(browser, testInfo, 'fresh-login', loginPage => login(loginPage, email, password))
  await freshSession(browser, testInfo, 'recovery', async recoveryPage => {
    await recoveryPage.goto('/recuperar-palavra-passe')
    await recoveryPage.getByLabel('Email', { exact: true }).fill(email)
    const recoveryRequestedAt = Date.now()
    await recoveryPage.getByRole('button', { name: 'Enviar código', exact: true }).click()
    await expect(recoveryPage.getByRole('heading', { name: 'Introduza o código', exact: true })).toBeVisible()
    const recovery = await deliveredMail('admin', criteria(recoveryRequestedAt, /^\d{6} is your reset password code$/))
    await recoveryPage.getByLabel('Código de verificação', { exact: true }).fill(recovery.code)
    await recoveryPage.getByRole('button', { name: 'Verificar código', exact: true }).click()
    await recoveryPage.getByLabel('Nova palavra-passe', { exact: true }).fill(recoveredPassword)
    await recoveryPage.getByLabel('Confirmar palavra-passe', { exact: true }).fill(recoveredPassword)
    await recoveryPage.getByRole('button', { name: 'Guardar e entrar', exact: true }).click()
    await expectIdentity(recoveryPage, email)
  })
  await freshSession(browser, testInfo, 'old-password-rejected', (loginPage, runtime) => rejectOldPassword(loginPage, runtime, testInfo, email, password))
  await freshSession(browser, testInfo, 'recovered-login', async (loginPage, runtime) => {
    await login(loginPage, email, recoveredPassword)
    await importOriginalData(loginPage, testInfo)
    const imported = await verifyImportedData(loginPage, original)
    const converted = await inviteImportedTeacher(loginPage, original, imported, teacherEmail)
    const invitation = await deliveredMail('teacher', {
      recipient: teacherEmail, senders: ['invitations@cronos.pt'],
      subject: new RegExp(`^Invitation to join Cronos Aceitação ${runId}$`), purpose: 'invitation',
      after: converted.requestedAt, before: converted.requestedAt + 120_000,
      linkHosts: ['clerk.cronos.pt'], linkPath: '/v1/tickets/accept',
    })
    let preferenceSlot
    await freshSession(browser, testInfo, 'teacher-invitation', async teacherPage => {
      await teacherPage.goto(invitation.link)
      await expect(teacherPage).toHaveURL(/^https:\/\/cronos\.pt\/(login|register)(?:[/?#]|$)/)
      if (new URL(teacherPage.url()).pathname.startsWith('/login')) {
        await teacherPage.getByRole('link', { name: /Registar|Criar conta/ }).click()
      }
      await expect(teacherPage.getByLabel('Palavra-passe', { exact: true })).toBeVisible()
      for (const [label, value] of [['Nome', 'Cronos'], ['Apelido', 'Professor'], ['Email', teacherEmail]]) {
        const field = teacherPage.getByLabel(label, { exact: true })
        if (await field.isVisible() && await field.isEditable()) await field.fill(value)
      }
      await teacherPage.getByLabel('Palavra-passe', { exact: true }).fill(teacherPassword)
      const consent = teacherPage.getByRole('checkbox', { name: /poderes para a vincular/ })
      if (await consent.isVisible()) await consent.check()
      await teacherPage.getByRole('button', { name: 'Continuar', exact: true }).click()
      await expectIdentity(teacherPage, teacherEmail)
      await provenance.recordCurrentActor(teacherPage)
      await teacherPage.goto('/my-schedules')
      await expect(teacherPage).toHaveURL(/\/my-schedules$/)
      preferenceSlot = await saveTeacherPreference(teacherPage)
      await expect(teacherPage.getByRole('button', { name: 'Terminar sessão', exact: true })).toBeVisible()
      await teacherPage.getByRole('button', { name: 'Terminar sessão', exact: true }).click()
      await expect.poll(() => teacherPage.evaluate(() => Boolean(window.Clerk?.loaded && !window.Clerk.user && !window.Clerk.session))).toBe(true)
    })
    await freshSession(browser, testInfo, 'teacher-fresh-login', async teacherPage => {
      await login(teacherPage, teacherEmail, teacherPassword)
      await teacherPage.goto('/my-schedules')
      await expect(teacherPage).toHaveURL(/\/my-schedules$/)
      await verifyTeacherPreference(teacherPage, preferenceSlot)
      await verifyTeacherPermissions(teacherPage)
    })
    await loginPage.reload()
    await verifyAcceptedTeacher(loginPage, converted)
    await verifyAdminAvailability(loginPage, teacherEmail, preferenceSlot)
    await provenance.recordCreatedSchool(schoolType, loginPage)
    await archiveAndRestoreCampaignTeacher(loginPage, converted)
    await provenance.recordCreatedSchool(schoolType, loginPage)
    await exerciseRoomCrud(loginPage, runId)
    await exerciseSubjectCrud(loginPage, runId)
    await exerciseCourseAndInitialClass(loginPage, runId, Number(schoolPeriod.start.slice(0, 4)))
    await verifyAcceptedTeacher(loginPage, converted)
    const rejected = await generateProposal(loginPage, testInfo, original, imported)
    const rejectionStatus = await rejectUnpublishedProposal(loginPage, testInfo, rejected)
    await addAdminPreference(loginPage, testInfo, converted, preferenceSlot, rejectionStatus)
    const generated = await generateProposal(loginPage, testInfo, original, imported)
    expect(generated.proposal.proposal_id).not.toBe(rejected.proposal.proposal_id)
    expect(generated.versionId).not.toBe(rejected.versionId)
    await verifyFirstProposalAndApprove(loginPage, testInfo, generated, original, imported)
    let operationalHistory
    await freshSession(browser, testInfo, 'teacher-published-schedule-and-progress', async teacherPage => {
      await login(teacherPage, teacherEmail, teacherPassword)
      const { member, week } = await verifyPublishedTeacherSchedule(teacherPage, testInfo, generated, original, imported, converted)
      await verifyFutureExecutionAndIncompleteWeek(teacherPage, testInfo, week)
      await verifyInitialProgress(teacherPage, testInfo, original, imported, member.teacher_id)
      if (persistent) return
      await freshSession(browser, testInfo, 'concurrent-admin-occurrence-decision', async (concurrentPage, concurrentRuntime) => {
        await login(concurrentPage, email, recoveredPassword)
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
    await runtime.action('authenticated-404', [{ origin: 'https://cronos.pt', pathname: missingPath, method: 'GET', status: 404, action: 'authenticated-404' }], async () => {
      const response = await loginPage.goto(missingPath)
      expect(response.status()).toBe(404)
      await expect(loginPage.getByRole('heading', { name: 'Página não encontrada', exact: true })).toBeVisible()
    })
    await loginPage.getByRole('link', { name: 'Ir para o painel', exact: true }).click()
    await expect(loginPage).toHaveURL(/\/dashboard$/)
    await loginPage.getByRole('button', { name: 'Terminar sessão', exact: true }).click()
    await expect.poll(() => loginPage.evaluate(() => Boolean(window.Clerk?.loaded && !window.Clerk.user && !window.Clerk.session))).toBe(true)
    await loginPage.goto('/dashboard')
    await expect(loginPage).toHaveURL(/\/login(?:[/?#]|$)/)
    await expect(loginPage.getByLabel('Email', { exact: true })).toBeVisible()
  })
}
