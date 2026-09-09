import { createHash } from 'node:crypto'
import { readFile, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const backendLegalPath = resolve(process.cwd(), '..', 'backend', 'app', 'legal.py')
const legalContentPath = resolve(process.cwd(), 'src', 'features', 'legal', 'legal-content.json')
const legalManifestPath = resolve(process.cwd(), 'src', 'features', 'legal', 'legal-manifest.json')

const REQUIRED_DOCUMENTS = ['privacy', 'terms', 'dpa', 'cookies']
const DRAFT_MARKERS = [
  /\bTODO\b/i,
  /\bTBD\b/i,
  /deve ser confirmad[ao]/i,
  /antes da publicação/i,
  /pré-lançamento/i,
  /por confirmar/i,
  /a confirmar/i,
]

function stableStringify(value) {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(',')}}`
  }
  return JSON.stringify(value)
}

export function canonicalDocumentDigest(document) {
  return createHash('sha256').update(stableStringify(document), 'utf8').digest('hex')
}

export function buildLegalManifest(legalContent, previousManifest = {}) {
  const documents = Object.fromEntries(
    Object.entries(legalContent.documents).map(([name, document]) => [name, {
      version: document.version,
      sha256: canonicalDocumentDigest(document),
    }]),
  )
  const versions = Object.fromEntries(
    Object.entries(previousManifest.versions ?? {}).map(([name, entries]) => [name, { ...entries }]),
  )
  for (const [name, document] of Object.entries(documents)) {
    versions[name] ??= {}
    versions[name][document.version] ??= document.sha256
  }
  return {
    format: 'cronos-legal-manifest-v1',
    version: legalContent.version,
    documents,
    versions,
  }
}

function allDocumentText(legalContent) {
  return Object.values(legalContent?.documents ?? {}).flatMap((document) => [
    document.title,
    document.intro,
    ...document.sections.flatMap(({ title, body }) => [title, body]),
    ...(document.annexes ?? []).flatMap((annex) => [
      annex.title,
      annex.body ?? '',
      ...(annex.items ?? []).flatMap((item) => Object.values(item)),
    ]),
  ]).join('\n')
}

export function validateLegalVersionContract({ backendSource, legalContent, legalManifest }) {
  const termsVersion = backendSource.match(/CURRENT_TERMS_VERSION\s*=\s*["']([^"']+)["']/)?.[1]
  const dpaVersion = backendSource.match(/CURRENT_DPA_VERSION\s*=\s*["']([^"']+)["']/)?.[1]
  const privacyVersion = backendSource.match(/CURRENT_PRIVACY_VERSION\s*=\s*["']([^"']+)["']/)?.[1]
  const errors = []

  if (!termsVersion || !dpaVersion || !privacyVersion) errors.push('Backend legal versions are missing.')
  if (!legalContent?.version || !legalContent?.documents) errors.push('Canonical legal content is missing.')
  if (legalManifest?.format !== 'cronos-legal-manifest-v1') errors.push('Legal manifest format is invalid.')
  if (termsVersion !== dpaVersion || termsVersion !== privacyVersion || termsVersion !== legalContent?.version) {
    errors.push(`Legal version mismatch: backend terms=${termsVersion}, backend dpa=${dpaVersion}, backend privacy=${privacyVersion}, content=${legalContent?.version}`)
  }

  const actualDocuments = Object.keys(legalContent?.documents ?? {}).sort()
  if (JSON.stringify(actualDocuments) !== JSON.stringify([...REQUIRED_DOCUMENTS].sort())) {
    errors.push(`Canonical documents must be exactly: ${REQUIRED_DOCUMENTS.join(', ')}.`)
  }
  if (JSON.stringify(Object.keys(legalManifest?.documents ?? {}).sort()) !== JSON.stringify([...REQUIRED_DOCUMENTS].sort())) {
    errors.push(`Legal manifest must contain exactly: ${REQUIRED_DOCUMENTS.join(', ')}.`)
  }
  if (JSON.stringify(Object.keys(legalManifest?.versions ?? {}).sort()) !== JSON.stringify([...REQUIRED_DOCUMENTS].sort())) {
    errors.push(`Legal manifest history must contain exactly: ${REQUIRED_DOCUMENTS.join(', ')}.`)
  }

  for (const name of REQUIRED_DOCUMENTS) {
    const document = legalContent?.documents?.[name]
    const manifestEntry = legalManifest?.documents?.[name]
    const history = legalManifest?.versions?.[name]
    if (!document || !manifestEntry || !history) continue
    if (document.version !== legalContent.version || manifestEntry.version !== document.version) {
      errors.push(`Legal document ${name} has an inconsistent version.`)
    }
    const digest = canonicalDocumentDigest(document)
    if (manifestEntry.sha256 !== digest) {
      errors.push(`Legal document ${name} changed without a versioned manifest digest update.`)
    }
    if (history[document.version] !== digest) {
      errors.push(`Legal document ${name} reuses a version with a different digest.`)
    }
  }

  const contentText = allDocumentText(legalContent ?? { documents: {} })
  for (const marker of DRAFT_MARKERS) {
    if (marker.test(contentText)) errors.push(`Legal content contains an unresolved draft marker: ${marker}`)
  }
  const dpaText = stableStringify(legalContent?.documents?.dpa ?? {})
  for (const annex of ['Anexo A', 'Anexo B', 'Anexo C', 'Anexo D']) {
    if (!dpaText.includes(annex)) errors.push(`DPA is missing ${annex}.`)
  }

  if (errors.length) throw new Error(errors.join('\n'))
  return { version: termsVersion, documents: REQUIRED_DOCUMENTS }
}

export async function readLegalContractSources() {
  const [backendSource, legalContentSource] = await Promise.all([
    readFile(backendLegalPath, 'utf8'),
    readFile(legalContentPath, 'utf8'),
  ])
  let legalManifestSource = '{}'
  try {
    legalManifestSource = await readFile(legalManifestPath, 'utf8')
  } catch (error) {
    if (!process.argv.includes('--write') || error.code !== 'ENOENT') throw error
  }
  return {
    backendSource,
    legalContent: JSON.parse(legalContentSource),
    legalManifest: JSON.parse(legalManifestSource),
  }
}

const invokedScript = process.argv[1] && resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url))
if (invokedScript) {
  const sources = await readLegalContractSources()
  if (process.argv.includes('--write')) {
    sources.legalManifest = buildLegalManifest(sources.legalContent, sources.legalManifest)
  }

  const result = validateLegalVersionContract(sources)
  if (process.argv.includes('--write')) {
    await writeFile(legalManifestPath, `${JSON.stringify(sources.legalManifest, null, 2)}\n`)
  }
  console.log(`Legal version contract passed: ${result.version}; ${result.documents.length} documents hashed`)
}
