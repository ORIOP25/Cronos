import { copyFile, readFile, writeFile } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'
import { canonicalMarketingRoutes, marketingMetadata } from '../src/features/marketing/content/metadata.js'
import { publicIdentity } from '../src/features/marketing/content/publicIdentity.js'
import { PUBLIC_ASSET_REVISION, publicAsset } from '../src/utils/publicAsset.js'

const scriptDirectory = dirname(fileURLToPath(import.meta.url))
const defaultDistDirectory = join(scriptDirectory, '..', 'dist')
const projectRoot = resolve(scriptDirectory, '..')
const notFoundMarkdownPath = join(projectRoot, 'public', '404.md')

const metadataSelectors = [
  ['title', /<title\b[^>]*>[\s\S]*?<\/title>/i],
  ['meta[name="description"]', /<meta\b(?=[^>]*\bname\s*=\s*["']description["'])[^>]*\/?\s*>/i],
  ['link[rel="canonical"]', /<link\b(?=[^>]*\brel\s*=\s*["']canonical["'])[^>]*\/?\s*>/i],
  ['meta[property="og:title"]', /<meta\b(?=[^>]*\bproperty\s*=\s*["']og:title["'])[^>]*\/?\s*>/i],
  ['meta[property="og:description"]', /<meta\b(?=[^>]*\bproperty\s*=\s*["']og:description["'])[^>]*\/?\s*>/i],
  ['meta[property="og:url"]', /<meta\b(?=[^>]*\bproperty\s*=\s*["']og:url["'])[^>]*\/?\s*>/i],
  ['meta[name="twitter:title"]', /<meta\b(?=[^>]*\bname\s*=\s*["']twitter:title["'])[^>]*\/?\s*>/i],
  ['meta[name="twitter:description"]', /<meta\b(?=[^>]*\bname\s*=\s*["']twitter:description["'])[^>]*\/?\s*>/i],
]

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[character])
}

function findMetadataElement(html, label, pattern) {
  const matches = [...html.matchAll(new RegExp(pattern.source, 'gi'))]
  if (matches.length === 0) throw new Error(`Missing metadata element: ${label}`)
  if (matches.length > 1) throw new Error(`Expected one metadata element: ${label}`)
  return matches[0][0]
}

function replaceMetadataElement(html, label, pattern, replacement) {
  findMetadataElement(html, label, pattern)
  return html.replace(pattern, replacement)
}

function organizationJsonLd() {
  return {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'WebSite',
        '@id': 'https://cronos.pt/#website',
        url: 'https://cronos.pt/',
        name: publicIdentity.brand,
        alternateName: 'cronos.pt',
        publisher: { '@id': 'https://cronos.pt/#organization' },
      },
      {
        '@type': 'SoftwareApplication',
        '@id': 'https://cronos.pt/#software',
        name: publicIdentity.brand,
        url: 'https://cronos.pt/',
        applicationCategory: 'EducationalApplication',
        operatingSystem: 'Web Browser',
        description: 'Cronos ajuda escolas profissionais a gerir horários, faltas e substituições.',
      },
      {
        '@type': 'Organization',
        '@id': 'https://cronos.pt/#organization',
        name: publicIdentity.brand,
        url: 'https://cronos.pt/',
        logo: `https://cronos.pt${publicAsset('/logo.png')}`,
        founder: {
          '@type': 'Person',
          name: publicIdentity.operator.name,
          jobTitle: publicIdentity.operator.role,
        },
        contactPoint: [{
          '@type': 'ContactPoint',
          email: publicIdentity.email,
          contactType: 'customer support',
          areaServed: publicIdentity.address.country,
          availableLanguage: 'Portuguese',
        }],
        address: {
          '@type': 'PostalAddress',
          streetAddress: publicIdentity.address.street,
          postalCode: publicIdentity.address.postalCode,
          addressLocality: publicIdentity.address.locality,
          addressCountry: publicIdentity.address.country,
        },
      },
    ],
  }
}

export function renderOrganizationJsonLd(html) {
  const pattern = /<script\s+id=["']cronos-organization-jsonld["'][^>]*>[\s\S]*?<\/script>/i
  if (!pattern.test(html)) throw new Error('Missing Organization JSON-LD script marker.')
  const json = JSON.stringify(organizationJsonLd())
    .replace(/</g, '\\u003c')
    .replace(/>/g, '\\u003e')
    .replace(/&/g, '\\u0026')
  return html.replace(pattern, `<script id="cronos-organization-jsonld" type="application/ld+json">${json}</script>`)
}

function addMarketingStylesheet(html, href) {
  if (!href) return html
  const escapedHref = href.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const linkPattern = new RegExp(`<link\\s+rel=["']stylesheet["']\\s+href=["']${escapedHref}["']\\s*/?>`, 'gi')
  const matches = [...html.matchAll(linkPattern)]
  if (matches.length > 1) throw new Error(`Expected one MarketingLayout stylesheet link, found ${matches.length}.`)
  if (matches.length === 1) return html
  if (!/<\/head>/i.test(html)) throw new Error('Cannot add MarketingLayout stylesheet without a closing head tag.')
  return html.replace(/<\/head>/i, `  <link rel="stylesheet" href="${escapeHtml(href)}" />\n</head>`)
}

export function renderMarketingPage(html, metadata, marketingCssHref) {
  let rendered = html
  rendered = replaceMetadataElement(rendered, 'title', metadataSelectors[0][1], `<title>${escapeHtml(metadata.title)}</title>`)
  rendered = replaceMetadataElement(rendered, 'meta[name="description"]', metadataSelectors[1][1], `<meta name="description" content="${escapeHtml(metadata.description)}" />`)
  rendered = replaceMetadataElement(rendered, 'link[rel="canonical"]', metadataSelectors[2][1], `<link rel="canonical" href="${escapeHtml(metadata.canonicalUrl)}" />`)
  rendered = replaceMetadataElement(rendered, 'meta[property="og:title"]', metadataSelectors[3][1], `<meta property="og:title" content="${escapeHtml(metadata.title)}" />`)
  rendered = replaceMetadataElement(rendered, 'meta[property="og:description"]', metadataSelectors[4][1], `<meta property="og:description" content="${escapeHtml(metadata.description)}" />`)
  rendered = replaceMetadataElement(rendered, 'meta[property="og:url"]', metadataSelectors[5][1], `<meta property="og:url" content="${escapeHtml(metadata.canonicalUrl)}" />`)
  rendered = replaceMetadataElement(rendered, 'meta[name="twitter:title"]', metadataSelectors[6][1], `<meta name="twitter:title" content="${escapeHtml(metadata.title)}" />`)
  rendered = replaceMetadataElement(rendered, 'meta[name="twitter:description"]', metadataSelectors[7][1], `<meta name="twitter:description" content="${escapeHtml(metadata.description)}" />`)
  return addMarketingStylesheet(rendered, marketingCssHref)
}

export function resolveMarketingStylesheet(manifest) {
  const entry = Object.entries(manifest).find(([key, value]) => key === 'src/features/marketing/components/layout/MarketingLayout.jsx' || value?.src === 'src/features/marketing/components/layout/MarketingLayout.jsx')?.[1]
  const stylesheet = entry?.css?.find((href) => /^assets\/[^/]+-[a-z0-9]+\.css$/i.test(href))
  if (!stylesheet) throw new Error('Vite manifest is missing the hashed MarketingLayout stylesheet.')
  return `/${stylesheet}`
}

async function readMarketingStylesheet(distDirectory) {
  const manifestPath = join(distDirectory, '.vite', 'manifest.json')
  return resolveMarketingStylesheet(JSON.parse(await readFile(manifestPath, 'utf8')))
}

function validatePublicAssetRevision(html, route) {
  const assetUrls = [...html.matchAll(/(?:src|href|content)=["']([^"']*(?:\/logo\.png|\/favicon\.[^"']+|\/og-cronos\.png|\/marketing\/)[^"']*)["']/gi)].map(([, url]) => url)
  const expectedRevision = `?v=${PUBLIC_ASSET_REVISION}`
  if (assetUrls.some((url) => !url.includes(expectedRevision))) throw new Error(`${route} contains an unversioned public asset.`)
  if (!html.includes(`https://cronos.pt${publicAsset('/logo.png')}`)) throw new Error(`${route} is missing the versioned Organization logo.`)
}

function validateMetadataCatalog() {
  const routes = Object.keys(marketingMetadata)
  if (!routes.includes('/')) throw new Error('Marketing metadata is missing the homepage route.')
  if (routes.some((route) => !route.startsWith('/'))) throw new Error('Marketing metadata contains an invalid route.')

  const canonicalUrls = canonicalMarketingRoutes.map((route) => marketingMetadata[route]?.canonicalUrl)
  if (canonicalUrls.some((url) => !url)) throw new Error('Marketing metadata is missing a canonical route.')
  if (canonicalUrls.some((url) => !url.startsWith('https://cronos.pt'))) throw new Error('Marketing canonical URLs must use https://cronos.pt.')
  if (new Set(canonicalUrls).size !== canonicalUrls.length) throw new Error('Marketing canonical URLs must be unique.')
  for (const route of routes) {
    if (!marketingMetadata[route].canonicalUrl.startsWith('https://cronos.pt')) throw new Error('Marketing canonical URLs must use https://cronos.pt.')
    if (!canonicalMarketingRoutes.some((canonicalRoute) => `https://cronos.pt${canonicalRoute}` === marketingMetadata[route].canonicalUrl)) {
      throw new Error(`Marketing metadata alias points outside the canonical route set: ${route}`)
    }
  }
}

function validateRenderedMetadata(html, metadata) {
  const expectedValues = [
    `<title>${escapeHtml(metadata.title)}</title>`,
    `<meta name="description" content="${escapeHtml(metadata.description)}" />`,
    `<link rel="canonical" href="${escapeHtml(metadata.canonicalUrl)}" />`,
    `<meta property="og:title" content="${escapeHtml(metadata.title)}" />`,
    `<meta property="og:description" content="${escapeHtml(metadata.description)}" />`,
    `<meta property="og:url" content="${escapeHtml(metadata.canonicalUrl)}" />`,
    `<meta name="twitter:title" content="${escapeHtml(metadata.title)}" />`,
    `<meta name="twitter:description" content="${escapeHtml(metadata.description)}" />`,
  ]
  for (const expectedValue of expectedValues) {
    if (!html.includes(expectedValue)) throw new Error(`Rendered marketing HTML is missing: ${expectedValue}`)
  }
}

function replaceRootMarkup(html, markup) {
  const marker = '<div id="root"></div>'
  const occurrences = html.split(marker).length - 1
  if (occurrences !== 1) throw new Error(`Expected one root marker, found ${occurrences}.`)
  return html.replace(marker, `<div id="root">${markup}</div>`)
}

function stripBuildOnlyMarkup(html) {
  return html
    .replace(/<script\b[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style\b[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&(?:amp|lt|gt|quot|#39);/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function validateHeadings(html, route) {
  const headings = [...html.matchAll(/<h([1-6])\b[^>]*>([\s\S]*?)<\/h\1>/gi)].map(([, level]) => Number(level))
  if (headings.filter((level) => level === 1).length !== 1) throw new Error(`${route} must contain exactly one H1.`)
  for (let index = 1; index < headings.length; index += 1) {
    if (headings[index] - headings[index - 1] > 1) throw new Error(`${route} contains a heading level jump.`)
  }
}

function validateSemanticRoute(html, route, minimumCharacters = 0) {
  validateHeadings(html, route)
  const text = stripBuildOnlyMarkup(html)
  if (text.length < minimumCharacters) throw new Error(`${route} contains only ${text.length} meaningful characters; expected at least ${minimumCharacters}.`)
}

function validateGeneratedRoutes(generatedPages) {
  for (const [route, html] of generatedPages) {
    const minimumCharacters = route === '/' || ['/sobre', '/about', '/contacto', '/contact', '/privacidade', '/privacy'].includes(route) ? 500 : 0
    validateSemanticRoute(html, route, minimumCharacters)
  }
}

export async function buildMarketingPages(distDirectory = defaultDistDirectory) {
  validateMetadataCatalog()
  const indexPath = join(distDirectory, 'index.html')
  const template = renderOrganizationJsonLd(await readFile(indexPath, 'utf8'))
  const marketingCssHref = await readMarketingStylesheet(distDirectory)
  const vite = await createServer({ root: projectRoot, appType: 'custom', server: { middlewareMode: true }, logLevel: 'error' })
  const generatedPages = new Map()

  try {
    const { renderPublicRoute, renderStaticNotFound } = await vite.ssrLoadModule('/src/features/marketing/renderPublicRoute.jsx')
    for (const [route, metadata] of Object.entries(marketingMetadata)) {
      const html = renderMarketingPage(replaceRootMarkup(template, renderPublicRoute(route)), metadata, marketingCssHref)
      validateRenderedMetadata(html, metadata)
      validatePublicAssetRevision(html, route)
      generatedPages.set(route, html)
      const filename = route === '/' ? 'index.html' : `${route.slice(1)}.html`
      await writeFile(join(distDirectory, filename), html)
    }

    const notFoundHtml = replaceRootMarkup(template, renderStaticNotFound())
    validateSemanticRoute(notFoundHtml, '404', 20)
    await writeFile(join(distDirectory, '404.html'), notFoundHtml)
    await copyFile(notFoundMarkdownPath, join(distDirectory, '404.md'))
  } finally {
    await vite.close()
  }

  validateGeneratedRoutes(generatedPages)
}

export { organizationJsonLd }

const invokedScript = process.argv[1] && resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url))
if (invokedScript) {
  try {
    await buildMarketingPages()
    console.log(`Marketing pages built: ${Object.keys(marketingMetadata).join(', ')}`)
  } catch (error) {
    console.error(error instanceof Error ? error.message : error)
    process.exitCode = 1
  }
}
