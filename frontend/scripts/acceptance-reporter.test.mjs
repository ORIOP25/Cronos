import assert from 'node:assert/strict'
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import AcceptanceReporter from '../e2e/acceptance-reporter.js'

test('reporter records concrete cases and keeps retries, missing proof and test failures visible', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'cronos-reporter-'))
  try {
    const outputFile = join(directory, 'result.json')
    const reporter = new AcceptanceReporter({ outputFile, artifactRoot: directory })
    reporter.onBegin()
    const descriptor = { annotations: [{ type: 'acceptance-case', description: 'E2E-01/founder-registration' }] }
    reporter.onTestEnd(descriptor, {
      status: 'passed', retry: 0, startTime: new Date('2026-10-07T09:00:00Z'), duration: 1200,
      attachments: [
        { name: 'acceptance-proof', body: Buffer.from(JSON.stringify({ case_id: 'E2E-01/founder-registration', eligible: true, ui_provenance: true })) },
        { name: 'trace', path: join(directory, 'trace.zip') },
      ],
    })
    reporter.onTestEnd(descriptor, { status: 'passed', retry: 1, startTime: new Date(), duration: 1, attachments: [] })
    reporter.onTestEnd({ annotations: [] }, { status: 'failed', retry: 0, startTime: new Date(), duration: 1, attachments: [] })
    await reporter.onEnd({ status: 'failed' })
    const report = JSON.parse(await readFile(outputFile, 'utf8'))
    assert.equal(report.playwright_status, 'failed')
    assert.equal(report.cases.length, 2)
    assert.deepEqual(report.cases[0], {
      id: 'E2E-01/founder-registration', requirement: 'E2E-01', name: 'founder-registration', status: 'passed', attempts: 1,
      started_at: '2026-10-07T09:00:00.000Z', finished_at: '2026-10-07T09:00:01.200Z', eligible: true, ui_provenance: true, evidence: ['trace.zip'],
    })
    assert.equal(report.cases[1].attempts, 2)
    assert.equal(report.cases[1].eligible, false)
    assert.deepEqual(report.cases[1].evidence, [])
    assert.ok(report.failures.includes('Test without a concrete acceptance case'))
  } finally { await rm(directory, { recursive: true, force: true }) }
})

test('reporter refuses unknown case IDs, ambiguous proof and evidence outside the artifact root', () => {
  const reporter = new AcceptanceReporter({ outputFile: join(tmpdir(), 'unused.json'), artifactRoot: join(tmpdir(), 'evidence') })
  reporter.onBegin()
  reporter.onTestEnd({ annotations: [{ type: 'acceptance-case', description: 'E2E-01/unknown' }] }, { status: 'passed', retry: 0, startTime: new Date(), duration: 1, attachments: [] })
  reporter.onTestEnd({ annotations: [{ type: 'acceptance-case', description: 'E2E-01/founder-registration' }] }, {
    status: 'passed', retry: 0, startTime: new Date(), duration: 1,
    attachments: [
      { name: 'trace', path: join(tmpdir(), 'outside.zip') },
      ...[true, false].map(eligible => ({ name: 'acceptance-proof', body: Buffer.from(JSON.stringify({ case_id: 'E2E-01/founder-registration', eligible, ui_provenance: true })) })),
    ],
  })
  assert.equal(reporter.cases[0].eligible, false)
  assert.deepEqual(reporter.cases[0].evidence, [])
  assert.equal(reporter.failures.length, 3)
})
