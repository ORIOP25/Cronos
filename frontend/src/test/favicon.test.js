import { Buffer } from 'node:buffer'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const frontendRoot = resolve(import.meta.dirname, '../..')
const indexHtml = readFileSync(resolve(frontendRoot, 'index.html'), 'utf8')
const headers = readFileSync(resolve(frontendRoot, 'public/_headers'), 'utf8').replaceAll('\r\n', '\n')
const favicon = readFileSync(resolve(frontendRoot, 'public/favicon.png'))

describe('public favicon contract', () => {
  it('uses the dedicated favicon instead of the transparent brand logo', () => {
    expect(indexHtml).toContain('<link rel="icon" type="image/png" sizes="256x256" href="/favicon.png?v=3" />')
    expect(indexHtml).not.toContain('<link rel="icon" type="image/png" sizes="256x256" href="/logo.png" />')
    expect(indexHtml).toContain('<link rel="apple-touch-icon" sizes="256x256" href="/favicon.png?v=3" />')
  })

  it('publishes the favicon with a stable cache rule and valid PNG dimensions', () => {
    expect(headers).toContain('/favicon.png\n  Cache-Control: public, max-age=86400')
    expect(favicon.subarray(0, 8)).toEqual(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))
    expect(favicon.readUInt32BE(16)).toBe(256)
    expect(favicon.readUInt32BE(20)).toBe(256)
  })
})
