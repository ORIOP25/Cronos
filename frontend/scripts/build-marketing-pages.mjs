import { readFile, writeFile } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { marketingMetadata } from '../src/features/marketing/content/metadata.js'

const scriptDirectory = dirname(fileURLToPath(import.meta.url))
const defaultDistDirectory = join(scriptDirectory, '..', 'dist')

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

export function renderMarketingPage(html, metadata) {
  let rendered = html
  rendered = replaceMetadataElement(rendered, 'title', metadataSelectors[0][1], `<title>${escapeHtml(metadata.title)}</title>`)
  rendered = replaceMetadataElement(rendered, 'meta[name="description"]', metadataSelectors[1][1], `<meta name="description" content="${escapeHtml(metadata.description)}" />`)
  rendered = replaceMetadataElement(rendered, 'link[rel="canonical"]', metadataSelectors[2][1], `<link rel="canonical" href="${escapeHtml(metadata.canonicalUrl)}" />`)
  rendered = replaceMetadataElement(rendered, 'meta[property="og:title"]', metadataSelectors[3][1], `<meta property="og:title" content="${escapeHtml(metadata.title)}" />`)
  rendered = replaceMetadataElement(rendered, 'meta[property="og:description"]', metadataSelectors[4][1], `<meta property="og:description" content="${escapeHtml(metadata.description)}" />`)
  rendered = replaceMetadataElement(rendered, 'meta[property="og:url"]', metadataSelectors[5][1], `<meta property="og:url" content="${escapeHtml(metadata.canonicalUrl)}" />`)
  rendered = replaceMetadataElement(rendered, 'meta[name="twitter:title"]', metadataSelectors[6][1], `<meta name="twitter:title" content="${escapeHtml(metadata.title)}" />`)
  rendered = replaceMetadataElement(rendered, 'meta[name="twitter:description"]', metadataSelectors[7][1], `<meta name="twitter:description" content="${escapeHtml(metadata.description)}" />`)
  return rendered
}

function validateMetadataCatalog() {
  const routes = Object.keys(marketingMetadata)
  if (!routes.includes('/')) throw new Error('Marketing metadata is missing the homepage route.')
  if (routes.some((route) => !route.startsWith('/'))) throw new Error('Marketing metadata contains an invalid route.')

  const canonicalUrls = routes.map((route) => marketingMetadata[route].canonicalUrl)
  if (canonicalUrls.some((url) => !url.startsWith('https://cronos.pt'))) throw new Error('Marketing canonical URLs must use https://cronos.pt.')
  if (new Set(canonicalUrls).size !== canonicalUrls.length) throw new Error('Marketing canonical URLs must be unique.')
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

export async function buildMarketingPages(distDirectory = defaultDistDirectory) {
  validateMetadataCatalog()
  const indexPath = join(distDirectory, 'index.html')
  const template = await readFile(indexPath, 'utf8')

  for (const [route, metadata] of Object.entries(marketingMetadata)) {
    const html = renderMarketingPage(template, metadata)
    validateRenderedMetadata(html, metadata)
    const filename = route === '/' ? 'index.html' : `${route.slice(1)}.html`
    await writeFile(join(distDirectory, filename), html)
  }
}

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
