import { join } from 'node:path'
import { validateProductionConfig } from '../frontend/e2e/utils/acceptance-policy.js'
import { productionDependencies } from './real-browser-preflight.mjs'

export const ACCEPTANCE_PROJECT = 'acceptance'
export const ACCEPTANCE_WORKERS = 1

export function acceptancePlan(environment, artifactDir) {
  const config = validateProductionConfig(environment)
  const missing = productionDependencies(environment)
  if (!environment.E2E_SECRET_REGISTRY) missing.push('E2E_SECRET_REGISTRY')
  if (missing.length) return { status: 'dependency_unavailable', missing }
  if (Buffer.from(environment.E2E_ARTIFACT_KEY, 'base64').length !== 32) {
    throw new Error('Evidence key must contain exactly 32 random bytes')
  }
  return {
    status: 'ready',
    config,
    project: ACCEPTANCE_PROJECT,
    workers: ACCEPTANCE_WORKERS,
    reportPath: join(artifactDir, 'acceptance-report.json'),
    artifactRoot: join(artifactDir, 'acceptance-artifacts'),
    resultPath: join(artifactDir, 'acceptance-result.json'),
  }
}

export function acceptanceExitCode(status) {
  if (status === 'validated') return 0
  if (status === 'dependency_unavailable') return 3
  return 1
}

function deploymentSnapshot(phase, result, checkedAt) {
  if (result?.status !== 'ready' || !result.components || !Object.keys(result.components).length) return null
  return { phase, checked_at: result.checked_at ?? checkedAt, components: { ...result.components }, deployments: { ...(result.deployments ?? {}) } }
}

export function assembleCampaign({ runId, testsRevision, expectedRevision, startedAt, finishedAt, before, after, playwrightReport, cleanup }) {
  const report = playwrightReport ?? { failures: ['Acceptance reporter produced no report'], cases: [] }
  return {
    schema_version: 1,
    run_id: runId,
    mode: 'acceptance',
    tests_revision: testsRevision,
    expected_revision: expectedRevision,
    started_at: startedAt,
    finished_at: finishedAt,
    deployments: [deploymentSnapshot('before', before, startedAt), deploymentSnapshot('after', after, finishedAt)].filter(Boolean),
    data_verified: before?.status === 'ready' && before.data !== undefined && before.data !== null,
    evidence_protected: false,
    cleanup: cleanup ?? { status: 'pending' },
    failures: [...(report.failures ?? [])],
    cases: report.cases ?? [],
  }
}
