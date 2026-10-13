// @vitest-environment node
import fs from 'node:fs'
import { describe, expect, it } from 'vitest'

const headers = fs.readFileSync('public/_headers', 'utf8').replaceAll('\r\n', '\n')
const html = fs.readFileSync('index.html', 'utf8')
const nginx = fs.readFileSync('nginx.conf', 'utf8')
const nginxCi = fs.readFileSync('nginx.ci.conf', 'utf8')
const worker = fs.readFileSync('public/_worker.js', 'utf8')

describe('production browser boundary', () => {
  it('ships the required static security headers', () => {
    expect(headers.startsWith('/*')).toBe(true)
    for (const value of ["frame-ancestors 'none'", 'X-Frame-Options: DENY', 'nosniff', 'Strict-Transport-Security: max-age=31536000; includeSubDomains', 'Referrer-Policy', 'Permissions-Policy', 'https://api.cronos.pt', 'https://clerk.cronos.pt', 'https://*.protect.clerk.com', 'https://challenges.cloudflare.com']) expect(headers).toContain(value)
    expect(headers).not.toMatch(/localhost|clerk\.accounts\.dev|unsafe-eval|frame-ancestors 'self'/)
    expect(html).not.toContain('Content-Security-Policy')
    expect(nginx).toContain("add_header Content-Security-Policy \"default-src 'self';")
    expect(nginx).toContain('add_header X-Frame-Options DENY always;')
    expect(nginx).toContain('add_header X-Content-Type-Options nosniff always;')
    expect(nginx).toContain('add_header Referrer-Policy strict-origin-when-cross-origin always;')
    expect(nginx).toContain('add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;')
    expect(nginx).toContain('add_header Strict-Transport-Security $hsts_value always;')
    expect(nginx).toContain('https "max-age=31536000; includeSubDomains";')
  })

  it('keeps the three host adapters aligned on public routing', () => {
    for (const config of [nginx, nginxCi]) {
      expect(config).toContain('charset_types text/html text/markdown;')
      expect(config).toContain('error_page 404 =404 $not_found_asset;')
      expect(config).toContain('try_files $uri $uri.html =404;')
      expect(config.match(/try_files \/index\.html =404;/g)).toHaveLength(1)
      expect(config.match(/try_files \/app-shell\.html =404;/g)).toHaveLength(5)
      expect(config).toContain('text/markdown')
      expect(config).toContain('location @homepage_markdown')
      expect(config).toContain('foundation(?:/waiting)?')
    }
    expect(fs.existsSync('public/_redirects')).toBe(false)
  })

  it('applies equivalent browser security policy at the edge', () => {
    expect(worker).toContain("'Content-Security-Policy'")
    expect(worker).toContain("'Strict-Transport-Security'")
    expect(worker).toContain("'X-Frame-Options'")
    expect(worker).toContain("'X-Content-Type-Options'")
    expect(worker).toContain("'Referrer-Policy'")
    expect(worker).toContain("'Permissions-Policy'")
  })

  it('declares cache policy by asset class', () => {
    expect(headers).toContain('/assets/*\n  Cache-Control: public, max-age=31536000, immutable')
    expect(headers).toContain('/logo.png\n  Cache-Control: no-cache, max-age=0, must-revalidate')
    expect(headers).toContain('/favicon.*\n  Cache-Control: no-cache, max-age=0, must-revalidate')
    expect(headers).toContain('/marketing/*\n  Cache-Control: no-cache, max-age=0, must-revalidate')
    expect(headers).toContain('/index.html\n  Cache-Control: no-store')
    expect(headers).toContain('/404.html\n  Cache-Control: no-store')
  })
})

function directives(csp) {
  return Object.fromEntries(csp.split(';')
    .map((part) => part.trim().split(/\s+/).filter(Boolean))
    .filter((tokens) => tokens.length)
    .map((tokens) => [tokens[0], tokens.slice(1)]))
}

function headerCsp(source) {
  return source.match(/^\s*Content-Security-Policy:\s*(.+)$/m)?.[1].trim()
}

function workerCsp(source) {
  return source.match(/'Content-Security-Policy':\s*"([^"]+)"/)?.[1]
}

function nginxCsp(source) {
  return source.match(/add_header Content-Security-Policy "([^"]+)" always;/)?.[1]
}

describe('Clerk protect port is scoped to connect-src only', () => {
  const targets = [
    ['public/_headers', headerCsp(headers)],
    ['public/_worker.js', workerCsp(worker)],
    ['nginx.conf', nginxCsp(nginx)],
    ['nginx.ci.conf', nginxCsp(nginxCi)],
  ]

  it.each(targets)('%s allows every protect port only for connections', (_name, csp) => {
    expect(typeof csp).toBe('string')
    const parsed = directives(csp)
    expect(parsed['connect-src']).toContain('https://*.protect.clerk.com:*')
    expect(parsed['connect-src']).not.toContain('https://*.protect.clerk.com')
    for (const directive of ['script-src', 'frame-src']) {
      expect(parsed[directive]).toContain('https://*.protect.clerk.com')
      expect(parsed[directive]).not.toContain('https://*.protect.clerk.com:*')
    }
    expect(parsed['default-src']).toEqual(["'self'"])
    expect(parsed['object-src']).toEqual(["'none'"])
    expect(parsed['frame-ancestors']).toEqual(["'none'"])
    expect(parsed['form-action']).toEqual(["'self'"])
    expect(parsed['upgrade-insecure-requests']).toEqual([])
  })
})

describe('frontend Docker build context', () => {
  const dockerignore = fs.readFileSync('.dockerignore', 'utf8')
    .replaceAll('\r\n', '\n').split('\n').map((line) => line.trim())
    .filter((line) => line && !line.startsWith('#'))

  it('excludes local diagnostics and keeps every secret folder or env file', () => {
    for (const entry of ['.test-artifacts/', '.auth/', '.env', '.env.*', '.git/', 'node_modules/', 'dist/', 'coverage/']) {
      expect(dockerignore).toContain(entry)
    }
  })
})
