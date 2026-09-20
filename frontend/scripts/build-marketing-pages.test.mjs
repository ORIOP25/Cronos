import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { renderMarketingPage, renderOrganizationJsonLd } from './build-marketing-pages.mjs'
import { canonicalMarketingRoutes, marketingMetadata } from '../src/features/marketing/content/metadata.js'
import { PUBLIC_ASSET_REVISION, publicAsset } from '../src/utils/publicAsset.js'

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

test('adds exactly one hashed MarketingLayout stylesheet to each public page', () => {
  const html = renderMarketingPage(fixture, metadata, '/assets/marketing-layout-abc12345.css')
  const links = html.match(/<link rel="stylesheet" href="\/assets\/marketing-layout-[^"]+\.css" \/>/g)
  assert.equal(links?.length, 1)
  assert.match(links[0], /marketing-layout-abc12345\.css/)
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
  assert.deepEqual(routes, canonicalMarketingRoutes)
  assert.deepEqual(canonicalMarketingRoutes.map((route) => marketingMetadata[route].canonicalUrl), routes.map((route) => `https://cronos.pt${route}`))
  assert.deepEqual(Object.keys(marketingMetadata).filter((route) => !canonicalMarketingRoutes.includes(route)), ['/about', '/contact', '/privacy'])

  const sourceIndex = readFileSync(resolve('index.html'), 'utf8')
  assert.doesNotMatch(sourceIndex, /"price"\s*:\s*"0"/)
  assert.match(sourceIndex, new RegExp(`favicon\\.png\\?v=${PUBLIC_ASSET_REVISION}`))
  assert.match(sourceIndex, new RegExp(`og-cronos\\.png\\?v=${PUBLIC_ASSET_REVISION}`))
  assert.equal(publicAsset('/logo.png'), `/logo.png?v=${PUBLIC_ASSET_REVISION}`)
})

test('builds Organization JSON-LD from the approved public identity', () => {
  const fixture = '<script id="cronos-organization-jsonld" type="application/ld+json"></script>'
  const html = renderOrganizationJsonLd(fixture)
  const json = JSON.parse(html.match(/>(\{[\s\S]*\})<\/script>/)[1])
  const organization = json['@graph'].find((node) => node['@id'] === 'https://cronos.pt/#organization')

  assert.equal(organization.contactPoint[0].email, 'contacto@cronos.pt')
  assert.equal(organization.contactPoint[0].contactType, 'customer support')
  assert.deepEqual(organization.address, {
    '@type': 'PostalAddress',
    streetAddress: 'R. dos Combatentes do Ultramar',
    postalCode: '2715-311',
    addressLocality: 'Pêro Pinheiro',
    addressCountry: 'PT',
  })
  assert.equal('telephone' in organization, false)
})

test('publishes agent discovery and machine-readable 404 content', () => {
  const llms = readFileSync(resolve('public/llms.txt'), 'utf8')
  const notFound = readFileSync(resolve('public/404.md'), 'utf8')
  assert.match(llms, /## Quando usar o Cronos/)
  assert.match(llms, /## Como usar o Cronos/)
  assert.match(llms, /https:\/\/cronos\.pt\/(?:sobre|contacto|privacidade)/)
  assert.match(llms, /contacto@cronos\.pt/)
  assert.match(llms, /R\. dos Combatentes do Ultramar/)
  assert.doesNotMatch(llms, /API pública/i)
  assert.match(notFound, /^# 404 — Página não encontrada/m)
  assert.match(notFound, /https:\/\/cronos\.pt\//)
  assert.match(notFound, /https:\/\/cronos\.pt\/llms\.txt/)
  assert.match(notFound, /https:\/\/cronos\.pt\/sitemap\.xml/)
})
