// @vitest-environment node
import fs from 'node:fs'
import { describe, expect, it } from 'vitest'

const headers = fs.readFileSync('public/_headers', 'utf8')
const html = fs.readFileSync('index.html', 'utf8')
const nginx = fs.readFileSync('nginx.conf', 'utf8')

describe('production browser boundary', () => {
  it('ships the required static security headers', () => {
    expect(headers.startsWith('/*')).toBe(true)
    for (const value of ["frame-ancestors 'none'", 'X-Frame-Options: DENY', 'nosniff', 'Referrer-Policy', 'Permissions-Policy', 'https://api.cronos.pt', 'https://clerk.cronos.pt', 'https://*.protect.clerk.com', 'https://challenges.cloudflare.com']) expect(headers).toContain(value)
    expect(headers).not.toContain('Strict-Transport-Security')
    expect(headers).not.toMatch(/localhost|clerk\.accounts\.dev|unsafe-eval|frame-ancestors 'self'/)
    expect(html).not.toContain('Content-Security-Policy')
    expect(nginx).toContain("add_header Content-Security-Policy \"frame-ancestors 'none'\" always;")
    expect(nginx).toContain('add_header X-Frame-Options DENY always;')
    expect(nginx).toContain('add_header X-Content-Type-Options nosniff always;')
  })
})
