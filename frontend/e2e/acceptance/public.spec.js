import AxeBuilder from '@axe-core/playwright'
import { test, expect } from './fixtures.js'

async function tabTo(page, control) {
  for (let count = 0; count < 40; count += 1) {
    await page.keyboard.press('Tab')
    if (await control.evaluate(element => element === document.activeElement)) break
  }
  await expect(control).toBeFocused()
}

test('native contact submission delivers every answer to the unchanged recipient', {
  annotation: { type: 'acceptance-case', description: 'E2E-16/contact-delivered' },
}, async ({ page, deliveredMail, registerSecret }, testInfo) => {
  test.setTimeout(300_000)
  const runId = process.env.E2E_RUN_ID
  expect(runId).toMatch(/^[a-z0-9-]{1,100}$/)
  expect(process.env.E2E_ADMIN_EMAIL).toBe('admincronos100@gmail.com')
  const email = `admincronos100+${runId}-contact@gmail.com`
  const marker = `e2e-contact-${runId}`
  const name = `Cronos Aceitação ${runId}`
  const fields = { Nome: name, Email: email, Telefone: 'Não indicado',
    Assunto: 'Criar horários do zero sem conflitos', Cursos: 'Entre 1 e 5', Professores: 'Entre 1 e 15', Mensagem: marker }
  expect((await page.goto('/contacto')).status()).toBe(200)
  for (const option of ['Começar', fields.Assunto, fields.Cursos, fields.Professores]) {
    await page.getByRole('button', { name: option, exact: true }).click()
  }
  await page.locator('#name').fill(name)
  await page.locator('#email').fill(email)
  await page.getByRole('button', { name: 'Continuar', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Quer acrescentar algum detalhe?', exact: true })).toBeVisible()
  await page.locator('#message').fill(marker)
  const challenge = page.locator('input[name="cf-turnstile-response"]')
  await expect(challenge).toHaveValue(/\S+/, { timeout: 120_000 })
  const token = await challenge.inputValue()
  await registerSecret(token)
  const after = Date.now()
  const requests = []
  const observe = request => {
    if (new URL(request.url()).pathname.startsWith('/api/v1/') && !['GET', 'HEAD', 'OPTIONS'].includes(request.method())) requests.push(request)
  }
  page.on('request', observe)
  try {
    const submitted = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/contact' && response.request().method() === 'POST')
    await page.getByRole('button', { name: 'Pedir demonstração', exact: true }).click()
    const response = await submitted
    expect(response.status()).toBe(204)
    expect(requests).toHaveLength(1)
    expect(requests[0]).toBe(response.request())
    expect(response.request().postDataJSON()).toEqual({ name, email, phone: '', message: marker, website: '',
      subject: fields.Assunto, courses: fields.Cursos, teachers: fields.Professores, turnstile_token: token })
    await expect(page.getByRole('heading', { name: `Pedido recebido, ${name}`, exact: true })).toBeVisible()
    const delivered = await deliveredMail('admin', { recipient: 'contacto@cronos.pt', purpose: 'contact',
      forwardedMailbox: process.env.E2E_ADMIN_EMAIL, replyTo: email, marker, fields,
      after, before: after + 180_000, senders: [process.env.E2E_CONTACT_SENDER || 'website@forms.cronos.pt'],
      subject: /^\[Cronos\] Novo contacto — Criar horários do zero sem conflitos$/,
    })
    expect(delivered).toMatchObject({ recipient: 'contacto@cronos.pt', reply_to: email, marker })
    expect(delivered.id).toBeTruthy()
    await testInfo.attach('contact-delivered-to-original-recipient', {
      body: Buffer.from(JSON.stringify({ submitted_at: new Date(after).toISOString(), fields, delivered,
        turnstile: 'native', original_recipient_unchanged: true, authenticated_forward_mailbox: process.env.E2E_ADMIN_EMAIL })), contentType: 'application/json',
    })
  } finally { page.off('request', observe) }
})

test('contact validation is reachable by keyboard and announces errors without submitting', {
  annotation: { type: 'acceptance-case', description: 'E2E-16/keyboard-focus-announcements' },
}, async ({ page }, testInfo) => {
  const response = await page.goto('/contacto')
  expect(response.status()).toBe(200)
  const writes = []
  const observe = request => {
    const url = new URL(request.url())
    if (url.pathname.startsWith('/api/v1/') && !['GET', 'HEAD', 'OPTIONS'].includes(request.method())) writes.push({ method: request.method(), path: url.pathname })
  }
  page.on('request', observe)
  try {
    for (const name of ['Começar', 'Criar horários do zero sem conflitos', 'Entre 1 e 5', 'Entre 1 e 15']) {
      const button = page.getByRole('button', { name, exact: true })
      await expect(button).toBeVisible()
      await tabTo(page, button)
      await button.press('Enter')
    }
    await expect(page.getByRole('heading', { name: 'Como podemos entrar em contacto?', exact: true })).toBeVisible()
    const next = page.getByRole('button', { name: 'Continuar', exact: true })
    await tabTo(page, next)
    await next.press('Enter')
    const name = page.locator('#name'), email = page.locator('#email')
    await expect(name).toBeFocused()
    await expect(name).toHaveAttribute('aria-invalid', 'true')
    await expect(name).toHaveAttribute('aria-describedby', 'name-error')
    await expect(page.getByRole('alert').filter({ hasText: /^Indique o seu nome\.$/ })).toBeVisible()
    await expect(page.getByRole('alert').filter({ hasText: /^Indique o seu email\.$/ })).toBeVisible()
    await name.pressSequentially('Cronos Aceitação')
    await page.keyboard.press('Tab')
    await expect(email).toBeFocused()
    await email.pressSequentially('email-invalido')
    await tabTo(page, next)
    await next.press('Enter')
    await expect(email).toBeFocused()
    await expect(email).toHaveAttribute('aria-invalid', 'true')
    await expect(email).toHaveAttribute('aria-describedby', 'email-error')
    await expect(page.getByRole('alert')).toHaveText('Indique um email válido.')
    await expect(name).toHaveAttribute('aria-invalid', 'false')
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
    expect(writes, 'Invalid contact details must not send any request').toEqual([])
    await testInfo.attach('keyboard-contact-validation', {
      body: Buffer.from(JSON.stringify({ focus: await email.getAttribute('id'), announcements: await page.getByRole('alert').allTextContents(), writes })), contentType: 'application/json',
    })
  } finally { page.off('request', observe) }
})

test('public routes render accessible content and keep canonical aliases', {
  annotation: { type: 'acceptance-case', description: 'E2E-16/public-routing' },
}, async ({ page }) => {
  test.setTimeout(90_000)
  for (const route of ['/', '/vantagens', '/como-funciona', '/sobre', '/ajuda', '/contacto']) {
    const response = await page.goto(route)
    expect(response.status(), route).toBe(200)
    await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await expect(page.getByRole('navigation', { name: 'Navegação principal' })).toBeVisible()
    expect((await new AxeBuilder({ page }).analyze()).violations, route).toEqual([])
  }
  for (const [alias, canonical] of [['/about', '/sobre'], ['/contact', '/contacto'], ['/privacy', '/privacidade']]) {
    const response = await page.goto(alias)
    expect(response.status(), alias).toBe(200)
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute('href', `https://cronos.pt${canonical}`)
  }
})

test('all public legal documents remain readable after reload', {
  annotation: { type: 'acceptance-case', description: 'E2E-16/legal-pages' },
}, async ({ page }) => {
  for (const route of ['/termos', '/privacidade', '/dpa', '/cookies']) {
    const response = await page.goto(route)
    expect(response.status(), route).toBe(200)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    const heading = await page.getByRole('heading', { level: 1 }).innerText()
    expect(heading.trim().length).toBeGreaterThan(5)
    expect((await page.getByRole('main').innerText()).length).toBeGreaterThan(500)
    await page.reload()
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(heading)
  }
})

test('unknown public routes return an actual 404 and offer a working home link', {
  annotation: { type: 'acceptance-case', description: 'E2E-16/public-404' },
}, async ({ page, runtime }) => {
  const pathname = '/acceptance-public-missing-path'
  await runtime.action('public-404', [{ origin: 'https://cronos.pt', pathname, method: 'GET', status: 404, action: 'public-404' }], async () => {
    const response = await page.goto(pathname)
    expect(response.status()).toBe(404)
    await expect(page.getByRole('heading', { name: 'Página não encontrada' })).toBeVisible()
  })
  await page.getByRole('link', { name: 'Voltar ao início', exact: true }).click()
  await expect(page).toHaveURL('https://cronos.pt/')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
})
