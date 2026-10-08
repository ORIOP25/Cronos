import assert from 'node:assert/strict'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import AcceptanceReporter from '../e2e/acceptance-reporter.js'

function annotation(description) {
  return { type: 'acceptance-case', description }
}

function proof(record) {
  return { name: 'acceptance-proof', body: Buffer.from(JSON.stringify(record)) }
}

function record(caseIds, evidence, startedAt, finishedAt) {
  return {
    schema_version: 2, case_ids: [caseIds].flat(), evidence,
    started_at: startedAt, finished_at: finishedAt, eligible: true, ui_provenance: true,
  }
}

function result(overrides = {}) {
  return {
    status: 'passed', retry: 0, startTime: new Date('2026-10-08T09:00:00Z'), duration: 5000,
    attachments: [], ...overrides,
  }
}

test('reporter binds each case to its own checkpoint and leaves absent checkpoints incomplete', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'cronos-reporter-'))
  try {
    const reporter = new AcceptanceReporter({ outputFile: join(directory, 'result.json'), artifactRoot: directory })
    reporter.onBegin()
    reporter.onTestEnd({ annotations: [annotation('E2E-01/founder-registration'), annotation('E2E-01/email-verification')] }, result({
      attachments: [
        proof(record('E2E-01/founder-registration', ['first.json'], '2026-10-08T09:00:01.000Z', '2026-10-08T09:00:02.000Z')),
        { name: 'independent-evidence', path: join(directory, 'first.json') },
      ],
    }))
    reporter.onTestEnd({ annotations: [annotation('E2E-04/delivered-invitation')] }, result({ status: 'failed' }))
    reporter.onTestEnd({ annotations: [annotation('E2E-04/invitation-acceptance')] }, result({ retry: 1 }))
    reporter.onTestEnd({ annotations: [] }, result())
    await reporter.onEnd({ status: 'failed' })
    assert.equal(reporter.failures.includes('Test without a concrete acceptance case'), true)
    assert.equal(reporter.cases.length, 4)
    const [founder, email, failed, retried] = reporter.cases
    assert.equal(founder.eligible, true)
    assert.equal(founder.ui_provenance, true)
    assert.deepEqual(founder.evidence, ['first.json'])
    assert.equal(founder.started_at, '2026-10-08T09:00:01.000Z')
    assert.equal(founder.finished_at, '2026-10-08T09:00:02.000Z')
    assert.equal(email.eligible, false)
    assert.equal(email.ui_provenance, false)
    assert.deepEqual(email.evidence, [])
    assert.equal(email.status, 'passed')
    assert.equal(failed.status, 'failed')
    assert.equal(failed.eligible, false)
    assert.equal(retried.eligible, false)
    assert.equal(retried.attempts, 2)
  } finally { await rm(directory, { recursive: true, force: true }) }
})

test('distinct variants keep their own bounded evidence and timestamps', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'cronos-reporter-'))
  try {
    const reporter = new AcceptanceReporter({ outputFile: join(directory, 'result.json'), artifactRoot: directory })
    reporter.onBegin()
    reporter.onTestEnd({ annotations: [annotation('E2E-16/public-routing'), annotation('E2E-16/legal-pages')] }, result({
      attachments: [
        proof(record('E2E-16/public-routing', ['routing.json'], '2026-10-08T09:00:01.000Z', '2026-10-08T09:00:02.000Z')),
        proof(record('E2E-16/legal-pages', ['legal.json'], '2026-10-08T09:00:03.000Z', '2026-10-08T09:00:04.000Z')),
        { name: 'routing', path: join(directory, 'routing.json') },
        { name: 'legal', path: join(directory, 'legal.json') },
      ],
    }))
    const [routing, legal] = reporter.cases
    assert.deepEqual(routing.evidence, ['routing.json'])
    assert.deepEqual(legal.evidence, ['legal.json'])
    assert.notEqual(routing.started_at, legal.started_at)
    assert.ok(Date.parse(legal.started_at) >= Date.parse(routing.finished_at))
  } finally { await rm(directory, { recursive: true, force: true }) }
})

test('reporter rejects unannotated or unknown checkpoint IDs and duplicate case lists', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'cronos-reporter-'))
  try {
    const reporter = new AcceptanceReporter({ outputFile: join(directory, 'result.json'), artifactRoot: directory })
    reporter.onBegin()
    reporter.onTestEnd({ annotations: [annotation('E2E-01/founder-registration')] }, result({
      attachments: [
        proof(record(['E2E-01/founder-registration', 'E2E-01/unknown'], ['first.json'], '2026-10-08T09:00:01.000Z', '2026-10-08T09:00:02.000Z')),
        { name: 'first', path: join(directory, 'first.json') },
      ],
    }))
    reporter.onTestEnd({ annotations: [annotation('E2E-01/email-verification')] }, result({
      attachments: [
        proof(record(['E2E-01/email-verification', 'E2E-01/email-verification'], ['first.json'], '2026-10-08T09:00:01.000Z', '2026-10-08T09:00:02.000Z')),
        { name: 'first', path: join(directory, 'first.json') },
      ],
    }))
    reporter.onTestEnd({ annotations: [annotation('E2E-01/foundation-completion')] }, result({
      attachments: [
        proof(record(['E2E-01/founder-registration'], ['first.json'], '2026-10-08T09:00:01.000Z', '2026-10-08T09:00:02.000Z')),
        { name: 'first', path: join(directory, 'first.json') },
      ],
    }))
    assert.ok(reporter.failures.some(message => /Unannotated acceptance proof/.test(message)))
    assert.ok(reporter.failures.some(message => /Invalid acceptance proof case list/.test(message)))
    assert.equal(reporter.cases.find(item => item.id === 'E2E-01/founder-registration').eligible, false)
    assert.equal(reporter.cases.find(item => item.id === 'E2E-01/email-verification').eligible, false)
    assert.equal(reporter.cases.find(item => item.id === 'E2E-01/foundation-completion').eligible, false)
  } finally { await rm(directory, { recursive: true, force: true }) }
})

test('unknown IDs, duplicate proofs, fabricated evidence and outside paths are rejected', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'cronos-reporter-'))
  try {
    const reporter = new AcceptanceReporter({ outputFile: join(directory, 'result.json'), artifactRoot: directory })
    reporter.onBegin()
    reporter.onTestEnd({ annotations: [annotation('E2E-01/unknown')] }, result())
    reporter.onTestEnd({ annotations: [annotation('E2E-01/founder-registration')] }, result({
      attachments: [
        proof(record('E2E-01/founder-registration', ['first.json'], '2026-10-08T09:00:01.000Z', '2026-10-08T09:00:02.000Z')),
        proof(record('E2E-01/founder-registration', ['first.json'], '2026-10-08T09:00:01.000Z', '2026-10-08T09:00:02.000Z')),
        { name: 'first', path: join(directory, 'first.json') },
      ],
    }))
    reporter.onTestEnd({ annotations: [annotation('E2E-01/email-verification')] }, result({
      attachments: [
        proof(record('E2E-01/email-verification', ['fabricated.json'], '2026-10-08T09:00:01.000Z', '2026-10-08T09:00:02.000Z')),
      ],
    }))
    reporter.onTestEnd({ annotations: [annotation('E2E-01/foundation-completion')] }, result({
      attachments: [
        proof(record('E2E-01/foundation-completion', ['../outside.json'], '2026-10-08T09:00:01.000Z', '2026-10-08T09:00:02.000Z')),
      ],
    }))
    reporter.onTestEnd({ annotations: [annotation('E2E-02/admin-login-logout')] }, result({
      attachments: [
        { name: 'acceptance-proof', body: Buffer.from('not json') },
        { name: 'trace', path: join(directory, '..', 'outside.zip') },
      ],
    }))
    assert.ok(reporter.failures.includes('Unknown acceptance case'))
    assert.ok(reporter.failures.some(message => /Ambiguous acceptance proof/.test(message)))
    assert.ok(reporter.failures.some(message => /Unmatched acceptance evidence/.test(message)))
    assert.ok(reporter.failures.some(message => /Invalid acceptance evidence/.test(message)))
    assert.ok(reporter.failures.includes('Invalid acceptance proof attachment'))
    assert.ok(reporter.failures.includes('Evidence is outside the artifact root'))
    const founder = reporter.cases.find(item => item.id === 'E2E-01/founder-registration')
    assert.equal(founder.eligible, false)
    assert.equal(reporter.cases.find(item => item.id === 'E2E-01/email-verification').eligible, false)
    assert.equal(reporter.cases.find(item => item.id === 'E2E-01/foundation-completion').eligible, false)
    assert.equal(reporter.cases.find(item => item.id === 'E2E-02/admin-login-logout').eligible, false)
  } finally { await rm(directory, { recursive: true, force: true }) }
})
