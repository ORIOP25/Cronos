import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { REQUIRED_CASES } from './utils/acceptance-policy.js'
import { PROOF_SCHEMA_VERSION, evidencePath, matchCaseProof, validateProofEvidence } from './utils/acceptance-proof.js'

const required = new Map(REQUIRED_CASES.map(item => [item.id, item]))

export default class AcceptanceReporter {
  constructor({ outputFile, artifactRoot }) {
    if (!outputFile || !artifactRoot) throw new Error('Explicit acceptance report and artifact paths required')
    this.outputFile = resolve(outputFile)
    this.artifactRoot = resolve(artifactRoot)
    this.cases = []
    this.failures = []
  }

  onBegin() { this.startedAt = new Date().toISOString() }

  onError() { this.failures.push('Playwright infrastructure failed') }

  onTestEnd(test, result) {
    const identifiers = test.annotations.filter(item => item.type === 'acceptance-case').map(item => item.description)
    if (!identifiers.length) this.failures.push('Test without a concrete acceptance case')
    const annotated = new Set(identifiers)
    const candidates = []
    const actualPaths = []
    for (const attachment of result.attachments) {
      if (attachment.name === 'acceptance-proof') {
        try {
          const value = JSON.parse(attachment.body.toString('utf8'))
          if (value?.schema_version !== PROOF_SCHEMA_VERSION) throw new Error('Unsupported acceptance proof schema')
          candidates.push(value)
        } catch { this.failures.push('Invalid acceptance proof attachment') }
      } else if (attachment.path) {
        const path = evidencePath(this.artifactRoot, attachment.path)
        if (path) actualPaths.push(path)
        else this.failures.push('Evidence is outside the artifact root')
      }
    }
    const records = []
    for (const value of candidates) {
      const caseIds = Array.isArray(value.case_ids) ? value.case_ids : []
      if (!caseIds.length || caseIds.some(id => typeof id !== 'string' || !id) || caseIds.length !== new Set(caseIds).size) {
        this.failures.push('Invalid acceptance proof case list')
        continue
      }
      const unannotated = caseIds.filter(id => !required.has(id) || !annotated.has(id))
      if (unannotated.length) {
        this.failures.push(`Unannotated acceptance proof: ${unannotated.join(', ')}`)
        continue
      }
      records.push(value)
    }
    for (const id of identifiers) {
      const descriptor = required.get(id)
      if (!descriptor) { this.failures.push('Unknown acceptance case'); continue }
      const { proof, failure } = matchCaseProof(id, records)
      if (failure) this.failures.push(failure)
      const { evidence, failures } = validateProofEvidence(proof, actualPaths, id)
      for (const message of failures) this.failures.push(message)
      const eligible = result.status === 'passed' && result.retry === 0
        && proof?.eligible === true && proof?.ui_provenance === true && failures.length === 0
      this.cases.push({
        ...descriptor,
        status: result.status === 'passed' ? 'passed' : result.status === 'skipped' ? 'skipped' : 'failed',
        attempts: result.retry + 1,
        started_at: proof?.started_at ?? result.startTime.toISOString(),
        finished_at: proof?.finished_at ?? new Date(result.startTime.getTime() + result.duration).toISOString(),
        eligible, ui_provenance: proof?.ui_provenance === true, evidence,
      })
    }
  }

  async onEnd(result) {
    if (result.status !== 'passed') this.failures.push('Playwright campaign did not pass')
    const report = { schema_version: 1, started_at: this.startedAt, finished_at: new Date().toISOString(), playwright_status: result.status, cases: this.cases, failures: this.failures }
    await mkdir(dirname(this.outputFile), { recursive: true })
    await writeFile(this.outputFile, `${JSON.stringify(report, null, 2)}\n`)
  }
}
