import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import {
  buildLegalManifest,
  validateLegalVersionContract,
} from './verify-legal-version-contract.mjs'

const backendSource = await readFile(resolve('..', 'backend', 'app', 'legal.py'), 'utf8')
const legalContent = JSON.parse(await readFile(resolve('src', 'features', 'legal', 'legal-content.json'), 'utf8'))

test('rejects changed legal content when the document version is unchanged', () => {
  const manifest = buildLegalManifest(legalContent)
  const changedContent = structuredClone(legalContent)
  changedContent.documents.privacy.sections[0].body += ' Texto alterado.'

  assert.throws(
    () => validateLegalVersionContract({ backendSource, legalContent: changedContent, legalManifest: manifest }),
    /changed without a versioned manifest digest update/,
  )
})

test('rejects a same-version manifest digest rewrite', () => {
  const changedContent = structuredClone(legalContent)
  changedContent.documents.privacy.sections[0].body += ' Texto alterado.'
  const tamperedManifest = structuredClone(buildLegalManifest(legalContent))
  tamperedManifest.documents.privacy.sha256 = buildLegalManifest(changedContent).documents.privacy.sha256

  assert.throws(
    () => validateLegalVersionContract({ backendSource, legalContent: changedContent, legalManifest: tamperedManifest }),
    /reuses a version with a different digest/,
  )
})

test('accepts a changed document only when its version and digest are updated', () => {
  const changedContent = structuredClone(legalContent)
  changedContent.version = '2026-02'
  changedContent.documents.privacy.version = '2026-02'
  changedContent.documents.privacy.sections[0].body += ' Texto alterado.'
  changedContent.documents.terms.version = '2026-02'
  changedContent.documents.dpa.version = '2026-02'
  changedContent.documents.cookies.version = '2026-02'
  const manifest = buildLegalManifest(changedContent)
  const changedBackendSource = backendSource
    .replace('CURRENT_TERMS_VERSION = "2026-01"', 'CURRENT_TERMS_VERSION = "2026-02"')
    .replace('CURRENT_DPA_VERSION = "2026-01"', 'CURRENT_DPA_VERSION = "2026-02"')
    .replace('CURRENT_PRIVACY_VERSION = "2026-01"', 'CURRENT_PRIVACY_VERSION = "2026-02"')

  assert.doesNotThrow(() => validateLegalVersionContract({
    backendSource: changedBackendSource,
    legalContent: changedContent,
    legalManifest: manifest,
  }))
})
