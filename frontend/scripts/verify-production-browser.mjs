import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const SITE = 'https://cronos.pt'

// Only the application's own resources count; third-party scripts and Clerk are
// judged by what the page visibly renders.
export function applicationFailure({ url, status, errorText }) {
  if (new URL(url).origin !== SITE) return null
  if (errorText) return errorText.includes('net::ERR_ABORTED') ? null : `${url} failed: ${errorText}`
  return status >= 400 ? `${url} answered ${status}` : null
}

// Read-only: opens public pages in a real browser, never signs in or submits.
async function main() {
  const { chromium } = await import('@playwright/test')
  const browser = await chromium.launch()
  const page = await browser.newPage()
  const failures = []
  const record = (failure) => { if (failure) failures.push(failure) }
  page.on('pageerror', (error) => failures.push(`JavaScript error: ${error.message}`))
  page.on('response', (response) => record(applicationFailure({ url: response.url(), status: response.status() })))
  page.on('requestfailed', (request) => record(applicationFailure({ url: request.url(), errorText: request.failure()?.errorText })))
  try {
    await page.goto(`${SITE}/`)
    await page.getByRole('heading', { level: 1, name: /Gestão de Horários/ }).waitFor()
    await page.goto(`${SITE}/login`)
    await page.getByLabel('Email', { exact: true }).waitFor({ timeout: 30_000 })
    await page.getByLabel('Palavra-passe', { exact: true }).waitFor()
  } catch (error) {
    failures.push(`Page did not render: ${error.message.split('\n')[0]}`)
  } finally {
    await browser.close()
  }
  for (const failure of failures) console.error(`::error::${failure}`)
  if (!failures.length) console.log('The public site and the login render in a real browser.')
  return failures.length ? 1 : 0
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().then((code) => { process.exitCode = code }, (error) => {
    console.error(error.message)
    process.exitCode = 1
  })
}
