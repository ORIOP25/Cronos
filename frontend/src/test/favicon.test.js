import { Buffer } from 'node:buffer'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { PUBLIC_ASSET_REVISION } from '../utils/publicAsset'

const frontendRoot = resolve(import.meta.dirname, '../..')
const indexHtml = readFileSync(resolve(frontendRoot, 'index.html'), 'utf8')
const headers = readFileSync(resolve(frontendRoot, 'public/_headers'), 'utf8').replaceAll('\r\n', '\n')
const favicon = readFileSync(resolve(frontendRoot, 'public/favicon.png'))

describe('public favicon contract', () => {
  it('uses the production-safe ICO as the browser tab icon', () => {
    expect(indexHtml).toContain(`<link rel="icon" type="image/x-icon" href="/favicon.ico?v=${PUBLIC_ASSET_REVISION}" />`)
    expect(indexHtml).not.toContain('<link rel="icon" type="image/png"')
    expect(indexHtml).not.toContain('<link rel="icon" type="image/png" sizes="256x256" href="/logo.png" />')
    expect(indexHtml).toContain(`<link rel="apple-touch-icon" sizes="256x256" href="/favicon.png?v=${PUBLIC_ASSET_REVISION}" />`)
  })

  it('publishes the favicon with revalidation and valid PNG dimensions', () => {
    expect(headers).toContain('/favicon.*\n  Cache-Control: no-cache, max-age=0, must-revalidate')
    expect(favicon.subarray(0, 8)).toEqual(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))
    expect(favicon.readUInt32BE(16)).toBe(256)
    expect(favicon.readUInt32BE(20)).toBe(256)
  })
})
