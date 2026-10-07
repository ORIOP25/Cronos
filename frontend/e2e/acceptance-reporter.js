import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, isAbsolute, relative, resolve, sep } from 'node:path'
import { REQUIRED_CASES } from './utils/acceptance-policy.js'

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
    const evidence = []
    const proofs = []
    for (const attachment of result.attachments) {
      if (attachment.name === 'acceptance-proof') {
        try { proofs.push(JSON.parse(attachment.body.toString('utf8'))) }
        catch { this.failures.push('Invalid acceptance proof attachment') }
      } else if (attachment.path) {
        const path = relative(this.artifactRoot, resolve(attachment.path))
        if (!path || path === '..' || path.startsWith(`..${sep}`) || isAbsolute(path)) this.failures.push('Evidence is outside the artifact root')
        else evidence.push(path.split(sep).join('/'))
      }
    }
    for (const id of identifiers) {
      const descriptor = required.get(id)
      if (!descriptor) { this.failures.push('Unknown acceptance case'); continue }
      const matching = proofs.filter(item => item?.case_id === id)
      if (matching.length > 1) this.failures.push(`Ambiguous acceptance proof: ${id}`)
      const proof = matching.length === 1 ? matching[0] : null
      this.cases.push({
        ...descriptor, status: result.status === 'passed' ? 'passed' : result.status === 'skipped' ? 'skipped' : 'failed',
        attempts: result.retry + 1,
        started_at: result.startTime.toISOString(), finished_at: new Date(result.startTime.getTime() + result.duration).toISOString(),
        eligible: proof?.eligible === true, ui_provenance: proof?.ui_provenance === true,
        evidence: [...new Set(evidence)],
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
