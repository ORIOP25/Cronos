import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { renderMarketingPage } from './build-marketing-pages.mjs'
import { marketingMetadata } from '../src/features/marketing/content/metadata.js'

const fixture = `<!doctype html>
<html><head>
<title>Original title</title>
<meta name="description" content="Original description">
<link rel="canonical" href="https://cronos.pt/">
<meta property="og:title" content="Original title">
<meta property="og:description" content="Original description">
<meta property="og:url" content="https://cronos.pt/">
<meta name="twitter:title" content="Original title">
<meta name="twitter:description" content="Original description">
<link rel="stylesheet" href="/assets/index.css">
</head><body><script type="module" src="/assets/index.js"></script></body></html>`

const metadata = {
  title: 'Vantagens | Cronos',
  description: 'Uma descrição da página.',
  canonicalUrl: 'https://cronos.pt/vantagens',
}

test('replaces all route metadata and preserves Vite assets', () => {
  const html = renderMarketingPage(fixture, metadata)

  assert.match(html, /<title>Vantagens \| Cronos<\/title>/)
  assert.match(html, /<meta name="description" content="Uma descrição da página\." \/>/)
  assert.match(html, /<link rel="canonical" href="https:\/\/cronos\.pt\/vantagens" \/>/)
  assert.match(html, /property="og:title" content="Vantagens \| Cronos"/)
  assert.match(html, /property="og:description" content="Uma descrição da página\."/)
  assert.match(html, /property="og:url" content="https:\/\/cronos\.pt\/vantagens"/)
  assert.match(html, /name="twitter:title" content="Vantagens \| Cronos"/)
  assert.match(html, /name="twitter:description" content="Uma descrição da página\."/)
  assert.match(html, /src="\/assets\/index\.js"/)
  assert.match(html, /href="\/assets\/index\.css"/)
})

test('fails explicitly when a required metadata tag is missing', () => {
  assert.throws(
    () => renderMarketingPage(fixture.replace('<meta name="description" content="Original description">', ''), metadata),
    /Missing metadata element: meta\[name="description"\]/,
  )
})

test('keeps the sitemap aligned with public metadata and does not publish a zero price', () => {
  const sitemap = readFileSync(resolve('public/sitemap.xml'), 'utf8')
  const routes = [...sitemap.matchAll(/<loc>https:\/\/cronos\.pt([^<]*)<\/loc>/g)].map(([, route]) => route)
  assert.deepEqual(routes, Object.keys(marketingMetadata))

  const sourceIndex = readFileSync(resolve('index.html'), 'utf8')
  assert.doesNotMatch(sourceIndex, /"price"\s*:\s*"0"/)
})
