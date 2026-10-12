import assert from 'node:assert/strict'
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs'
import test from 'node:test'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { randomBytes } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { protectEvidence, recoverEvidence } from './protect-test-evidence.mjs'
import { signRegistry } from './e2e-run-registry.mjs'
import { finalizeRun, verifyRunArtifacts } from './finalize-real-browser-run.mjs'
import { evaluatePreparation } from './prepare-history.mjs'
import { preparationFixture } from './preparation-test-fixture.mjs'
import {
  childSpec,
  cleanupOwnedResources,
  criticalPytestArgs,
  displayArgs,
  finalizePreparation,
  frontendFastArgs,
  frontendJunitEnv,
  isOwnedResource,
  parseArgs,
  parseCriticalManifest,
  preservePrimaryFailure,
  productionCampaignMode,
  ROOT,
  resolveE2eBaseUrl,
  runtimeProofFailures,
  summarizeJunit,
  validateDatabaseTargets,
  verifiedResultGuard,
} from './test.mjs'
import { redactSecrets, sanitizeCampaignDiagnostics, sanitizeDirectory } from './sanitize-test-artifacts.mjs'
import { classifyPath, collectFiles, countNonBlankLines, measureFiles } from './loc-report.mjs'

test('sanitizer CLI redacts separate campaign keys, OAuth identity and dynamic codes', () => {
  const directory = mkdtempSync(join(tmpdir(), 'cronos-cli-sanitize-'))
  try {
    const artifacts = join(directory, 'artifacts')
    mkdirSync(artifacts)
    const registry = join(directory, 'private-secrets.json')
    writeFileSync(registry, JSON.stringify(['452391']))
    const log = join(artifacts, 'failure.log')
    const signingKey = randomBytes(32).toString('base64')
    writeFileSync(log, `OAuth desktop-client-id signing ${signingKey} SSH dedicated-private-key code 452391`)
    const result = spawnSync(process.execPath, [join(ROOT, 'scripts/sanitize-test-artifacts.mjs'), artifacts], {
      encoding: 'utf8',
      env: { ...process.env, E2E_ARTIFACT_KEY: randomBytes(32).toString('base64'), E2E_RUN_ID: 'run-1', E2E_REGISTRY_HMAC_KEY: signingKey, E2E_ADMIN_SSH_KEY: 'dedicated-private-key', E2E_GMAIL_CLIENT_ID: 'desktop-client-id', E2E_SECRET_REGISTRY: registry },
    })
    assert.equal(result.status, 0, result.stderr)
    assert.equal(readFileSync(log, 'utf8'), 'OAuth [REDACTED] signing [REDACTED] SSH [REDACTED] code [REDACTED]')
  } finally { rmSync(directory, { recursive: true, force: true }) }
})

test('sanitizer CLI rejects an invalid secret registry before touching evidence', () => {
  const directory = mkdtempSync(join(tmpdir(), 'cronos-cli-sanitize-'))
  try {
    const artifacts = join(directory, 'artifacts')
    mkdirSync(artifacts)
    const registry = join(directory, 'private-secrets.json')
    writeFileSync(registry, JSON.stringify({ code: '452391' }))
    const source = join(artifacts, 'trace.zip')
    writeFileSync(source, 'private trace')
    const result = spawnSync(process.execPath, [join(ROOT, 'scripts/sanitize-test-artifacts.mjs'), artifacts], {
      encoding: 'utf8',
      env: { ...process.env, E2E_ARTIFACT_KEY: randomBytes(32).toString('base64'), E2E_RUN_ID: 'run-1', E2E_SECRET_REGISTRY: registry },
    })
    assert.notEqual(result.status, 0)
    assert.equal(readFileSync(source, 'utf8'), 'private trace')
    assert.equal(existsSync(`${source}.enc`), false)
  } finally { rmSync(directory, { recursive: true, force: true }) }
})

test('campaign diagnostics sanitize only the allowlisted JSON files and leave the sealed result untouched', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'cronos-diag-sanitize-'))
  try {
    const sealed = JSON.stringify({ run: { failures: ['delivered code 123456'] } })
    writeFileSync(join(directory, 'acceptance-result.json'), sealed)
    writeFileSync(join(directory, 'acceptance-plan.json'), `${JSON.stringify({ missing: ['none'], note: 'delivered code 123456' })}\n`)
    writeFileSync(join(directory, 'acceptance-cleanup.json'), '{"status":"completed"}\n')
    writeFileSync(join(directory, 'diagnostic-assessment.json'), '{"certifies_production":false}\n')
    writeFileSync(join(directory, 'artifact-verification.json'), '{"integrity":"verified","reason":null,"certifies_production":false}\n')
    writeFileSync(join(directory, 'ui-run-registry.json'), '{"actors":["user_x"],"secret":"123456"}\n')
    writeFileSync(join(directory, 'persistent-registry.json'), '{"key":"123456"}\n')
    await sanitizeCampaignDiagnostics(directory, ['123456'])
    assert.deepEqual(JSON.parse(readFileSync(join(directory, 'acceptance-plan.json'), 'utf8')), { missing: ['none'], note: 'delivered code [REDACTED]' })
    assert.equal(readFileSync(join(directory, 'acceptance-result.json'), 'utf8'), sealed)
    assert.equal(readFileSync(join(directory, 'acceptance-cleanup.json'), 'utf8'), '{"status":"completed"}\n')
    assert.equal(readFileSync(join(directory, 'diagnostic-assessment.json'), 'utf8'), '{"certifies_production":false}\n')
    assert.equal(readFileSync(join(directory, 'artifact-verification.json'), 'utf8'), '{"integrity":"verified","reason":null,"certifies_production":false}\n')
    assert.equal(readFileSync(join(directory, 'ui-run-registry.json'), 'utf8'), '{"actors":["user_x"],"secret":"123456"}\n')
    assert.equal(readFileSync(join(directory, 'persistent-registry.json'), 'utf8'), '{"key":"123456"}\n')
  } finally { rmSync(directory, { recursive: true, force: true }) }
})

test('campaign diagnostics refuse a non-regular allowlisted path', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'cronos-diag-sanitize-'))
  try {
    mkdirSync(join(directory, 'acceptance-plan.json'))
    await assert.rejects(sanitizeCampaignDiagnostics(directory, []), /regular file/)
  } finally { rmSync(directory, { recursive: true, force: true }) }
})

test('the sanitizer CLI redacts campaign diagnostics by allowlist and keeps the sealed result', () => {
  const directory = mkdtempSync(join(tmpdir(), 'cronos-diag-cli-'))
  try {
    const registry = join(directory, 'private-secrets.json')
    writeFileSync(registry, JSON.stringify(['452391']))
    writeFileSync(join(directory, 'acceptance-result.json'), '{"note":"code 452391"}\n')
    writeFileSync(join(directory, 'acceptance-plan.json'), '{"note":"code 452391"}\n')
    writeFileSync(join(directory, 'ui-run-registry.json'), '{"secret":"452391"}\n')
    const result = spawnSync(process.execPath, [join(ROOT, 'scripts/sanitize-test-artifacts.mjs'), '--diagnostics', directory], {
      encoding: 'utf8',
      env: { ...process.env, E2E_RUN_ID: 'run-1', E2E_SECRET_REGISTRY: registry },
    })
    assert.equal(result.status, 0, result.stderr)
    assert.deepEqual(JSON.parse(readFileSync(join(directory, 'acceptance-plan.json'), 'utf8')), { note: 'code [REDACTED]' })
    assert.equal(readFileSync(join(directory, 'acceptance-result.json'), 'utf8'), '{"note":"code 452391"}\n')
    assert.equal(readFileSync(join(directory, 'ui-run-registry.json'), 'utf8'), '{"secret":"452391"}\n')
  } finally { rmSync(directory, { recursive: true, force: true }) }
})

test('campaign diagnostics redact JSON values with finalizer semantics and stay well-formed', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'cronos-diag-json-'))
  try {
    const weird = 'x"y\\z\n'
    writeFileSync(join(directory, 'acceptance-plan.json'), `${JSON.stringify({ note: weird, code: 123456, total: 1234567 })}\n`)
    await sanitizeCampaignDiagnostics(directory, [weird, '123456', '234567'])
    assert.deepEqual(JSON.parse(readFileSync(join(directory, 'acceptance-plan.json'), 'utf8')), {
      note: '[REDACTED]', code: '[REDACTED]', total: 1234567,
    })
  } finally { rmSync(directory, { recursive: true, force: true }) }
})

test('campaign diagnostics fail closed on malformed JSON without touching bytes', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'cronos-diag-bad-'))
  try {
    const path = join(directory, 'acceptance-plan.json')
    writeFileSync(path, '{"note":"code 123456"')
    await assert.rejects(sanitizeCampaignDiagnostics(directory, ['123456']))
    assert.equal(readFileSync(path, 'utf8'), '{"note":"code 123456"')
  } finally { rmSync(directory, { recursive: true, force: true }) }
})

test('campaign diagnostics reject a junction that redirects outside the owned root', async () => {
  const root = mkdtempSync(join(tmpdir(), 'cronos-diag-root-'))
  const target = mkdtempSync(join(tmpdir(), 'cronos-diag-target-'))
  try {
    writeFileSync(join(target, 'acceptance-plan.json'), JSON.stringify({ note: 'code 123456' }))
    writeFileSync(join(target, 'ui-run-registry.json'), JSON.stringify({ secret: '123456' }))
    const link = join(root, 'linked')
    symlinkSync(target, link, 'junction')
    await assert.rejects(sanitizeCampaignDiagnostics(link, ['123456']), /confined/)
    assert.equal(readFileSync(join(target, 'acceptance-plan.json'), 'utf8'), JSON.stringify({ note: 'code 123456' }))
    assert.equal(readFileSync(join(target, 'ui-run-registry.json'), 'utf8'), JSON.stringify({ secret: '123456' }))
    rmSync(link, { force: true })
  } finally {
    rmSync(root, { recursive: true, force: true })
    rmSync(target, { recursive: true, force: true })
  }
})

test('the diagnostics sanitizer CLI refuses an empty directory list', () => {
  const result = spawnSync(process.execPath, [join(ROOT, 'scripts/sanitize-test-artifacts.mjs'), '--diagnostics'], {
    encoding: 'utf8',
    env: { ...process.env, E2E_RUN_ID: 'run-1', E2E_SECRET_REGISTRY: '' },
  })
  assert.notEqual(result.status, 0)
})

test('production JSON evidence uses the shared tree redaction and stays byte-exact when clean', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'cronos-prod-json-'))
  try {
    const key = randomBytes(32)
    const weird = 'pw"q\\r\ns'
    const clean = join(directory, 'clean.json')
    const dirty = join(directory, 'dirty.json')
    writeFileSync(clean, `${JSON.stringify({ ok: true, label: '€ café' })}\n`)
    const cleanBefore = readFileSync(clean, 'utf8')
    writeFileSync(dirty, `${JSON.stringify({ password: weird, code: 123456, total: 1234567, nested: { password: weird } })}\n`)
    await sanitizeDirectory(directory, [weird, '123456', '234567'], { key, runId: 'run-1' })
    assert.equal(readFileSync(clean, 'utf8'), cleanBefore)
    const value = JSON.parse(readFileSync(dirty, 'utf8'))
    assert.deepEqual(value, { password: '[REDACTED]', code: '[REDACTED]', total: 1234567, nested: { password: '[REDACTED]' } })
    const dirtyAfter = readFileSync(dirty, 'utf8')
    await sanitizeDirectory(directory, [weird, '123456', '234567'], { key, runId: 'run-1' })
    assert.equal(readFileSync(dirty, 'utf8'), dirtyAfter)
    assert.equal(readFileSync(clean, 'utf8'), cleanBefore)
  } finally { rmSync(directory, { recursive: true, force: true }) }
})

test('the isolated E2E frontend uses the Clerk test browser policy', () => {
  const compose = readFileSync(join(ROOT, 'docker-compose.test.yml'), 'utf8')
  assert.match(compose, /frontend:\s+build:\s+context: \.\/frontend\s+target: ci/)
})

test('parses forwarded runner arguments without rebuilding a shell command', () => {
  const parsed = parseArgs(['fast', '--scope', 'backend', '--', 'tests/unit/test name.py', '-q'])
  assert.equal(parsed.scope, 'backend')
  assert.deepEqual(parsed.forwarded, ['tests/unit/test name.py', '-q'])
})

test('rejects invalid arguments with usage code information', () => {
  assert.throws(() => parseArgs(['fast', '--scope', 'backend', '--scope', 'frontend']), /Only one --scope/)
  assert.throws(() => parseArgs(['e2e', '--project', 'unknown']), /Invalid E2E project/)
  assert.throws(() => parseArgs(['benchmark', '--profile', 'integration', '--scope', 'all']), /only valid for benchmark/)
  assert.equal(parseArgs(['benchmark', '--profile', 'fast', '--scope', 'frontend']).scope, 'frontend')
})

test('keeps capacity as an explicit E2E gate', () => {
  assert.equal(parseArgs(['capacity']).command, 'capacity')
  assert.equal(parseArgs(['capacity-smoke']).command, 'capacity-smoke')
  assert.equal(parseArgs(['e2e', '--project', 'capacity']).project, 'capacity')
})

test('selects the isolated and readonly projects and retires the faults alias', () => {
  assert.equal(parseArgs(['e2e', '--project', 'isolated']).project, 'isolated')
  assert.equal(parseArgs(['e2e', '--project', 'readonly']).project, 'readonly')
  assert.throws(() => parseArgs(['e2e', '--project', 'faults']), /Invalid E2E project/)
})

test('the fast frontend run selects every Vitest project, including dom-network data hooks', () => {
  assert.deepEqual(
    frontendFastArgs(['-t', 'getWeekSubmissionBlockers']),
    [
      'test', '--',
      '--project=node', '--project=dom', '--project=dom-network',
      '-t', 'getWeekSubmissionBlockers',
    ],
  )
})

test('each frontend runner wires its own JUnit report for truthful suite counts', () => {
  assert.deepEqual(frontendJunitEnv('vitest', 'frontend-fast.xml'), { VITEST_JUNIT_OUTPUT_FILE: 'frontend-fast.xml' })
  assert.deepEqual(frontendJunitEnv('playwright', 'e2e-all.xml'), { PLAYWRIGHT_JUNIT_OUTPUT_FILE: 'e2e-all.xml' })
  assert.deepEqual(frontendJunitEnv('vitest', null), {})
})

test('the critical manifest accepts explicit test paths and fails closed on invalid selections', () => {
  const valid = () => ({
    groups: [
      {
        name: 'unit',
        paths: [
          'tests/unit/test_scheduler_constraint_policy.py',
          'tests/unit/test_scheduler_typology_v1.py::test_forty_eight_classes_generate_a_complete_valid_schedule',
        ],
        args: ['--disable-socket'],
        workers: 4,
      },
      { name: 'db', paths: ['tests/integration/committed/test_worker_process_recovery.py'], workers: 1 },
    ],
    coverage: {
      sources: ['app/scheduler/domain/constraint_policy.py', 'app/scheduler/domain/candidate_validation.py'],
      fail_under: 80,
      includes: [
        { path: 'app/scheduler/domain/constraint_policy.py', fail_under: 100 },
        { path: 'app/scheduler/domain/candidate_validation.py', fail_under: 90 },
      ],
    },
  })

  const manifest = parseCriticalManifest(valid())
  assert.deepEqual(manifest.groups.map((group) => group.name), ['unit', 'db'])
  assert.deepEqual(manifest.groups[0].args, ['--disable-socket'])
  assert.equal(manifest.groups[0].paths[1], 'tests/unit/test_scheduler_typology_v1.py::test_forty_eight_classes_generate_a_complete_valid_schedule')
  assert.equal(manifest.groups[1].workers, 1)
  assert.equal(manifest.coverage.fail_under, 80)
  assert.deepEqual(manifest.coverage.sources, [
    'app/scheduler/domain/constraint_policy.py',
    'app/scheduler/domain/candidate_validation.py',
  ])

  assert.throws(() => parseCriticalManifest(null), /object/)
  assert.throws(() => parseCriticalManifest({ groups: [] }), /at least one group/)
  assert.throws(() => parseCriticalManifest({ ...valid(), coverage: { ...valid().coverage, sources: [] } }), /coverage.sources/)
  assert.throws(() => parseCriticalManifest({ ...valid(), coverage: { ...valid().coverage, sources: ['app/a.py', 'app/a.py'] } }), /duplicated/)
  assert.throws(
    () => parseCriticalManifest({ ...valid(), coverage: { sources: ['app/a.py'], includes: [{ path: 'app/scheduler/domain/constraint_policy.py', fail_under: 100 }] } }),
    /protected coverage gate/,
  )
  {
    const missing = valid()
    missing.coverage.includes = missing.coverage.includes.filter((entry) => !entry.path.endsWith('candidate_validation.py'))
    assert.throws(() => parseCriticalManifest(missing), /protected coverage gate/)
  }
  {
    const wrong = valid()
    wrong.coverage.includes = wrong.coverage.includes.map((entry) => (
      entry.path.endsWith('constraint_policy.py') ? { ...entry, fail_under: 99 } : entry
    ))
    assert.throws(() => parseCriticalManifest(wrong), /protected coverage gate/)
  }
  {
    const duplicate = valid()
    duplicate.groups = [{ name: 'unit', paths: ['tests/unit/a.py'] }, { name: 'unit', paths: ['tests/unit/b.py'] }]
    assert.throws(() => parseCriticalManifest(duplicate), /unique/)
  }
  assert.throws(() => parseCriticalManifest({ ...valid(), groups: [{ name: 'unit', paths: ['app/main.py'] }] }), /outside tests/)
  assert.throws(() => parseCriticalManifest({ ...valid(), groups: [{ name: 'Unit', paths: ['tests/unit/a.py'] }] }), /name/)

  assert.equal(parseArgs(['critical']).scope, 'backend')
  assert.equal(parseArgs(['critical', '--scope', 'backend']).command, 'critical')
  assert.throws(() => parseArgs(['critical', '--scope', 'all']), /backend/)
  assert.throws(() => parseArgs(['critical', '--scope', 'frontend']), /backend/)
})

test('the runtime proof guard fails closed on missing, skipped or wrong proof cases', () => {
  const required = [
    'test_an_owned_worker_never_duplicates_delivery_of_a_queued_job',
    'test_an_owned_worker_process_loss_is_recovered_by_a_real_supervisor',
    'test_forty_eight_classes_generate_a_complete_valid_schedule',
  ]
  const passed = `<testsuite tests="3">${
    required.map((name) => `<testcase classname="x" name="${name}" />`).join('')
  }</testsuite>`
  assert.deepEqual(runtimeProofFailures(passed, { minCollected: 3, required }), [])
  assert.ok(runtimeProofFailures('', { minCollected: 3, required }).includes('no test cases'))

  const skipped = `<testsuite tests="3">${
    required.map((name, index) => `<testcase classname="x" name="${name}">${index === 0 ? '<skipped />' : ''}</testcase>`).join('')
  }</testsuite>`
  assert.ok(runtimeProofFailures(skipped, { minCollected: 3, required }).some((failure) => /skipped/.test(failure)))

  const wrong = `<testsuite tests="3"><testcase classname="x" name="test_other" /></testsuite>`
  assert.ok(runtimeProofFailures(wrong, { minCollected: 3, required }).some((failure) => /missing case/.test(failure)))
  assert.ok(runtimeProofFailures(wrong, { minCollected: 3, required }).some((failure) => /collected 1 < 3/.test(failure)))
})

test('critical pytest arguments keep every manifest path as a separate native argument', () => {
  assert.deepEqual(
    criticalPytestArgs({ name: 'unit', paths: ['tests/unit/a.py', 'tests/unit/b.py'], args: ['--disable-socket'] }, 'report.xml'),
    ['tests/unit/a.py', 'tests/unit/b.py', '--disable-socket', '--junitxml=report.xml'],
  )
})

test('parses scheduler lab campaign options and rejects them elsewhere', () => {
  const parsed = parseArgs([
    'campaign',
    '--manifest', 'backend/tests/scheduler_lab/manifest.json',
    '--out', '.test-artifacts/lab',
    '--case', 'case-a',
    '--case', 'case-b',
    '--resume',
  ])
  assert.equal(parsed.command, 'campaign')
  assert.equal(parsed.manifest, 'backend/tests/scheduler_lab/manifest.json')
  assert.equal(parsed.out, '.test-artifacts/lab')
  assert.deepEqual(parsed.caseIds, ['case-a', 'case-b'])
  assert.equal(parsed.resume, true)
  assert.throws(() => parseArgs(['campaign', '--scope', 'backend']), /not valid for campaign/)
  assert.throws(() => parseArgs(['fast', '--manifest', 'x']), /only valid for campaign/)
  assert.throws(() => parseArgs(['campaign', '--unknown', 'x']), /Unknown option/)

  const generator = parseArgs(['campaign', '--mode', 'generator', '--time-limit', '5', '--workers', '2'])
  assert.equal(generator.mode, 'generator')
  assert.equal(generator.timeLimit, '5')
  assert.equal(generator.workers, '2')
  const repair = parseArgs(['campaign', '--mode', 'repair'])
  assert.equal(repair.mode, 'repair')
  const trajectory = parseArgs(['campaign', '--mode', 'trajectory'])
  assert.equal(trajectory.mode, 'trajectory')
  const longitudinal = parseArgs(['campaign', '--mode', 'longitudinal'])
  assert.equal(longitudinal.mode, 'longitudinal')
  assert.throws(() => parseArgs(['campaign', '--mode', 'unknown']), /Invalid campaign mode/)
  assert.throws(() => parseArgs(['campaign', '--workers', '0']), /Invalid worker count/)
})

test('production acceptance stays serialized and sanitizes its own artifact root', () => {
  const workflow = readFileSync(join(ROOT, '.github/workflows/acceptance.yml'), 'utf8')
  assert.match(workflow, /if: github\.ref == 'refs\/heads\/main' && \(/)
  assert.match(workflow, /group: cronos-production-acceptance/)
  assert.match(workflow, /cancel-in-progress: false/)
  assert.match(workflow, /E2E_RUN_ID: \$\{\{ github\.run_id \}\}-\$\{\{ github\.run_attempt \}\}/)
  assert.match(workflow, /sanitize-test-artifacts\.mjs "\.test-artifacts\/\$\{E2E_RUN_ID\}\/acceptance-artifacts"/)
  assert.match(workflow, /E2E_EXPECTED_REVISION: \$\{\{ github\.sha \}\}/)
  assert.doesNotMatch(workflow, /protect-test-evidence\.mjs protect/)
})

test('root CI keeps push on main while pull requests and manual dispatch run full checks', () => {
  const lines = readFileSync(join(ROOT, '.github/workflows/ci.yml'), 'utf8').split(/\r?\n/)
  const start = lines.indexOf('on:')
  assert.notEqual(start, -1, 'ci.yml must declare an on: trigger block')
  const end = lines.findIndex((line, index) => index > start && line !== '' && !/^\s/.test(line))
  assert.equal(
    lines.slice(start + 1, end).join('\n').trimEnd(),
    ['  push:', '    branches: [main]', '  pull_request:', '  workflow_dispatch:'].join('\n'),
  )
})

test('the frontend fast macro stays narrow and e2e-runtime owns the relocated mandatory checks', () => {
  const scripts = JSON.parse(readFileSync(join(ROOT, 'frontend/package.json'), 'utf8')).scripts
  const fast = scripts['verify:critical:fast']
  assert.ok(fast, 'verify:critical:fast must remain a developer macro')
  assert.match(fast, /npm run test:critical:coverage/, 'the critical coverage gate must stay in the fast macro')
  assert.doesNotMatch(fast, /npm run lint/, 'the full-source frontend lint belongs to e2e-runtime')
  assert.doesNotMatch(fast, /audit:production/, 'the production dependency audit belongs to e2e-runtime')
  assert.doesNotMatch(fast, /test:acceptance-infrastructure/, 'the acceptance infrastructure belongs to e2e-runtime')

  const lines = readFileSync(join(ROOT, '.github/workflows/ci.yml'), 'utf8').split(/\r?\n/)
  const runtimeStart = lines.indexOf('  e2e-runtime:')
  const aggregateStart = lines.indexOf('  e2e:')
  assert.notEqual(runtimeStart, -1, 'the e2e-runtime job must exist')
  assert.notEqual(aggregateStart, -1, 'the aggregate e2e job must exist')
  const runtime = lines.slice(runtimeStart, aggregateStart)
  // The YAML step block that owns a run line, from its `- name:` marker to the
  // next one. It lets the guard reject a step-level `if:` on the step itself,
  // not only a job-level condition.
  const stepBlock = (runLine) => {
    let start = runLine
    while (start > 0 && !/^      - /.test(runtime[start])) start -= 1
    let end = start + 1
    while (end < runtime.length && !/^      - /.test(runtime[end])) end += 1
    return runtime.slice(start, end)
  }
  const install = runtime.findIndex((line) => line.includes('Install frontend dependencies'))
  const lint = runtime.indexOf('        run: npm run lint')
  const audit = runtime.indexOf('        run: npm run audit:production')
  const infrastructure = runtime.indexOf('        run: npm run test:acceptance-infrastructure')
  assert.ok(
    install !== -1 && install < lint && lint < audit && install < infrastructure,
    'the relocated commands run after the frontend install',
  )
  assert.equal(runtime.some((line) => /^    if:/.test(line)), false, 'the e2e-runtime job must stay unconditional')
  for (const [label, runLine] of [['frontend lint', lint], ['production dependency audit', audit], ['acceptance infrastructure', infrastructure]]) {
    const block = stepBlock(runLine)
    assert.ok(block.includes('        working-directory: frontend'), `${label} runs in the frontend directory`)
    assert.equal(block.some((line) => /^        if:/.test(line)), false, `${label} step must stay unconditional`)
  }

  const aggregate = lines.slice(aggregateStart).join('\n')
  assert.match(aggregate, /needs: \[e2e-runtime, e2e-browser\]/)
  assert.match(aggregate, /if \[ "\$runtime" != "success" \]; then/)
})

test('exposes production acceptance as its own command', () => {
  assert.equal(parseArgs(['acceptance']).command, 'acceptance')
  assert.throws(() => parseArgs(['acceptance', '--project', 'acceptance']), /only valid for e2e/)
  assert.throws(() => parseArgs(['acceptance', '--', 'extra']), /not supported/)
})

test('public readonly diagnosis is an explicit command with no user selection filter', () => {
  assert.equal(parseArgs(['diagnose-public']).command, 'diagnose-public')
  assert.throws(() => parseArgs(['diagnose-public', '--project', 'acceptance']), /only valid for e2e/)
  assert.throws(() => parseArgs(['diagnose-public', '--grep', '@public-readonly']), /Unknown option/)
  assert.throws(() => parseArgs(['diagnose-public', '--', 'public.spec.js']), /not supported/)
  assert.throws(() => parseArgs(['unknown-mode']), /Unknown command/)
})

test('manual public diagnosis is allowed only on main without enabling the full campaign', () => {
  const workflow = readFileSync(join(ROOT, '.github/workflows/acceptance.yml'), 'utf8')
  const lines = workflow.split(/\r?\n/)
  const guard = lines.find(line => line.trimStart().startsWith('if: github.ref'))
  assert.equal(
    guard,
    "    if: github.ref == 'refs/heads/main' && (vars.E2E_ACCEPTANCE_ENABLED == 'true' || (github.event_name == 'workflow_dispatch' && (inputs.mode == 'prepare-history' || inputs.mode == 'diagnose-public'))) && !(github.event_name == 'workflow_dispatch' && inputs.mode == 'inspect-code-sender')",
  )
  assert.match(workflow, /- diagnose-public/)
  assert.ok(lines.includes('            .test-artifacts/${{ env.E2E_RUN_ID }}/diagnostic-assessment.json'))
  assert.equal(lines.some(line => /run\.json/.test(line)), false, 'the raw run report must stay outside the upload allowlist')
})

test('the workflow verifies the sealed result before upload and keeps only safe diagnostics', () => {
  const workflow = readFileSync(join(ROOT, '.github/workflows/acceptance.yml'), 'utf8')
  const lines = workflow.split(/\r?\n/)
  const blockAfter = (start) => {
    const rest = lines.slice(start + 1)
    const next = rest.findIndex(line => /^      - name:/.test(line))
    return (next === -1 ? rest : rest.slice(0, next)).join('\n')
  }
  assert.ok(lines.includes('        run: node scripts/sanitize-test-artifacts.mjs --diagnostics ".test-artifacts/${E2E_RUN_ID}"'))
  assert.ok(lines.includes('        run: node scripts/finalize-real-browser-run.mjs verify ".test-artifacts/${E2E_RUN_ID}/acceptance-result.json" ".test-artifacts/${E2E_RUN_ID}/acceptance-artifacts" ".test-artifacts/${E2E_RUN_ID}/artifact-verification.json"'))
  assert.ok(lines.includes("        if: always() && steps.sanitize.outcome == 'success' && steps.verify.outcome == 'success'"))
  assert.ok(lines.includes("        if: always() && steps.sanitize_diagnostics.outcome == 'success'"))
  assert.match(workflow, /steps\.sanitize\.outcome == 'success' && hashFiles\(format\('\.test-artifacts\/\{0\}\/acceptance-result\.json', env\.E2E_RUN_ID\)\)/)
  const rootStart = lines.indexOf('      - name: Upload protected acceptance artifacts')
  assert.notEqual(rootStart, -1, 'the protected upload must exist')
  assert.ok(blockAfter(rootStart).includes('acceptance-result.json'), 'the sealed result uploads with the verified root')
  const start = lines.indexOf('      - name: Upload sanitized acceptance diagnostics')
  assert.notEqual(start, -1, 'the safe diagnostics upload must exist')
  const diagnostics = blockAfter(start)
  assert.ok(diagnostics.includes('acceptance-plan.json'))
  assert.ok(diagnostics.includes("${{ steps.verify.outputs.receipt_available == 'true' && format('.test-artifacts/{0}/artifact-verification.json', env.E2E_RUN_ID) || '' }}"))
  assert.equal(diagnostics.includes('            .test-artifacts/${{ env.E2E_RUN_ID }}/artifact-verification.json'), false, 'the receipt uploads only through the availability flag')
  assert.equal(diagnostics.includes('acceptance-result.json'), false, 'the sealed result must not upload with unverified diagnostics')
  assert.equal(diagnostics.includes('acceptance-artifacts'), false, 'diagnostics must not upload the protected root')
})

test('manual code-sender inspection is a readonly workflow that cannot start the campaign', () => {
  const workflow = readFileSync(join(ROOT, '.github/workflows/acceptance.yml'), 'utf8')
  assert.match(workflow, /- inspect-code-sender/)
  assert.match(workflow, /node scripts\/inspect-e2e-code-sender\.mjs/)
  assert.match(workflow, /permissions:\r?\n  contents: read/)
  const lines = workflow.split(/\r?\n/)
  const start = lines.indexOf('  inspect-code-sender:')
  assert.notEqual(start, -1, 'the readonly inspection job must exist')
  const nextJob = lines.findIndex((line, index) => index > start && /^  [a-z][a-z0-9-]*:$/.test(line))
  const block = lines.slice(start, nextJob === -1 ? lines.length : nextJob).join('\n')
  assert.ok(block.includes('E2E_GMAIL_CLIENT_ID: ${{ secrets.E2E_GMAIL_CLIENT_ID }}'))
  assert.ok(block.includes('E2E_GMAIL_CLIENT_SECRET: ${{ secrets.E2E_GMAIL_CLIENT_SECRET }}'))
  // The runtime exposes one selected refresh token, never both mailboxes at once.
  const tokenLines = block.split('\n').filter(line => /REFRESH_TOKEN:/.test(line))
  assert.equal(tokenLines.length, 1, 'exactly one runtime refresh token may be exposed')
  assert.equal(tokenLines[0].trim(), "E2E_GMAIL_REFRESH_TOKEN: ${{ inputs.mailbox == 'teacher' && secrets.E2E_GMAIL_TEACHER_REFRESH_TOKEN || secrets.E2E_GMAIL_ADMIN_REFRESH_TOKEN }}")
  assert.match(block, /E2E_INSPECT_MAILBOX:/)
  assert.match(block, /E2E_INSPECT_PURPOSE:/)
  assert.match(block, /E2E_INSPECT_RECIPIENT:/)
  assert.doesNotMatch(block, /E2E_ADMIN_SSH_KEY|E2E_ARTIFACT_KEY|E2E_RAILWAY_TOKEN|playwright install|railway-v/)
  assert.doesNotMatch(block, /run\.json/)
  // Reset and alias diagnosis are available without another push.
  assert.match(workflow, /\r?\n      purpose:\r?\n/)
  assert.match(workflow, /\r?\n          - reset\r?\n/)
  assert.match(workflow, /\r?\n      recipient:\r?\n/)
})

test('the diagnose-public command exits three without contacting production when dependencies are missing', () => {
  const directory = mkdtempSync(join(tmpdir(), 'cronos-diag-plan-'))
  try {
    const result = spawnSync(process.execPath, [join(ROOT, 'scripts/test.mjs'), 'diagnose-public'], {
      cwd: ROOT, encoding: 'utf8', windowsHide: true,
      env: {
        ...process.env,
        TEST_ARTIFACT_DIR: directory,
        BASE_URL: 'https://cronos.pt',
        E2E_EXPECTED_REVISION: 'a'.repeat(40),
        E2E_ADMIN_EMAIL: 'admincronos100@gmail.com',
        E2E_TEACHER_EMAIL: 'professorcronos100@gmail.com',
        CLOUDFLARE_API_TOKEN: '', E2E_CLOUDFLARE_ACCOUNT_ID: '',
        E2E_RAILWAY_TOKEN: '', E2E_RAILWAY_TOKEN_TYPE: '',
        E2E_ARTIFACT_KEY: '', E2E_SECRET_REGISTRY: '', E2E_REGISTRY_HMAC_KEY: '',
      },
    })
    assert.equal(result.status, 3, result.stderr)
    const plan = JSON.parse(readFileSync(join(directory, 'acceptance-plan.json'), 'utf8'))
    assert.equal(plan.status, 'dependency_unavailable')
    assert.equal(plan.missing.includes('E2E_GMAIL_CODE_SENDER'), false)
    assert.equal(plan.missing.includes('E2E_ADMIN_SSH_KEY'), false)
    assert.ok(plan.missing.includes('CLOUDFLARE_API_TOKEN'))
  } finally { rmSync(directory, { recursive: true, force: true }) }
})

test('the shared production flow keeps the readonly diagnosis away from native SSH cleanup', () => {
  const diagnosis = productionCampaignMode('diagnose-public')
  assert.deepEqual(diagnosis, { preparation: false, diagnosis: true, cleanup: 'public_readonly', playwright: 'Playwright public readonly diagnosis' })
  for (const mode of ['acceptance', 'prepare-history']) {
    const spec = productionCampaignMode(mode)
    assert.equal(spec.cleanup, 'native_ssh')
    assert.equal(spec.diagnosis, false)
  }
  assert.equal(productionCampaignMode('acceptance').preparation, false)
  assert.equal(productionCampaignMode('prepare-history').preparation, true)
  assert.throws(() => productionCampaignMode('unknown'), /Unknown production mode/)
})

test('the production mode enum rejects inherited object labels before any effect', () => {
  for (const label of ['toString', 'constructor', 'valueOf', '__proto__', 'hasOwnProperty', 'unknown']) {
    assert.throws(() => productionCampaignMode(label), /Unknown production mode/)
  }
  assert.throws(() => productionCampaignMode(), /Unknown production mode/)
  assert.throws(() => productionCampaignMode({}), /Unknown production mode/)
  assert.equal(productionCampaignMode('acceptance').cleanup, 'native_ssh')
  assert.equal(productionCampaignMode('diagnose-public').cleanup, 'public_readonly')
})

test('the shared runner signs a captured Playwright process failure before finalizing', () => {
  const source = readFileSync(join(ROOT, 'scripts/test.mjs'), 'utf8')
  assert.match(source, /processFailed: Boolean\(playwrightError\)/)
  assert.doesNotMatch(source, /Playwright preparation did not pass/)
})

test('preserves paths and arguments containing spaces as separate child arguments', () => {
  const spec = childSpec('node', [ROOT, 'tests/with spaces/example.test.mjs'])
  assert.deepEqual(spec.args, [ROOT, 'tests/with spaces/example.test.mjs'])
})

test('redacts credentials from registered commands', () => {
  const output = displayArgs([
    'docker', 'exec', '-e', 'PGPASSWORD=secret', 'db',
    '-c', "CREATE ROLE app PASSWORD 'another-secret';",
    'postgresql+asyncpg://app:third-secret@127.0.0.1:5432/cronos_test_db',
  ])
  assert.doesNotMatch(output, /secret|another-secret|third-secret/)
  assert.match(output, /PGPASSWORD=\[redacted\]/)
  assert.match(output, /PASSWORD '\[redacted\]'/)
})

test('redacts fake secrets from text artifacts', () => {
  assert.equal(
    redactSecrets('token=fake-clerk-secret; keep this', ['fake-clerk-secret']),
    'token=[REDACTED]; keep this',
  )
  assert.equal(redactSecrets('verification code 123456', ['123456']), 'verification code [REDACTED]')
})

test('persistent preparation is an explicit command with no diagnostic selection flags', () => {
  assert.equal(parseArgs(['prepare-history']).command, 'prepare-history')
  assert.throws(() => parseArgs(['prepare-history', '--', 'identity.spec.js']), /not supported/)
})

test('production acceptance is excluded from default local E2E and explicitly enabled by its reporter', () => {
  const source = "import config from './playwright.config.js'; console.log(JSON.stringify(config.projects.map(({name,use,workers,retries})=>({name,channel:use?.channel,workers,retries}))))"
  function projects(baseUrl, report, preparationReport = '') {
    const result = spawnSync(process.execPath, ['--input-type=module', '-e', source], {
      cwd: join(ROOT, 'frontend'), windowsHide: true, encoding: 'utf8',
      env: { ...process.env, BASE_URL: baseUrl, E2E_ACCEPTANCE_REPORT: report, E2E_PREPARATION_REPORT: preparationReport },
    })
    assert.equal(result.status, 0, result.stderr)
    return JSON.parse(result.stdout)
  }
  assert.equal(projects('http://localhost:5173', '').some(project => project.name === 'acceptance'), false)
  assert.equal(projects('http://localhost:5173', '').some(project => project.name === 'preparation'), false)
  const acceptance = projects('https://cronos.pt', 'acceptance-report.json').find(project => project.name === 'acceptance')
  assert.deepEqual(acceptance, { name: 'acceptance', channel: 'chrome', workers: 1, retries: 0 })
  const preparation = projects('https://cronos.pt', '', 'preparation-report.json')
  assert.equal(preparation.some(project => project.name === 'acceptance'), false)
  assert.deepEqual(preparation.find(project => project.name === 'preparation'), { name: 'preparation', channel: 'chrome', workers: 1, retries: 0 })
})

test('production artifacts preserve encrypted traces and screenshots, without raw copies', async () => {
  const root = mkdtempSync(join(tmpdir(), 'cronos-protected-artifacts-'))
  const key = randomBytes(32)
  try {
    const trace = join(root, 'trace.zip')
    const screenshot = join(root, 'screenshot.png')
    writeFileSync(trace, 'opaque sensitive trace')
    writeFileSync(screenshot, Buffer.from([0, 1, 2, 3]))
    await sanitizeDirectory(root, [], { key, runId: 'run-1' })
    assert.equal(existsSync(trace), false)
    assert.equal(existsSync(screenshot), false)
    assert.equal(recoverEvidence(readFileSync(`${trace}.enc`), key, { run_id: 'run-1', path: 'trace.zip' }).toString(), 'opaque sensitive trace')
    assert.deepEqual(recoverEvidence(readFileSync(`${screenshot}.enc`), key, { run_id: 'run-1', path: 'screenshot.png' }), Buffer.from([0, 1, 2, 3]))
  } finally {
    rmSync(root, { force: true, recursive: true })
  }
})

test('a raw binary renamed to enc is not accepted as protected evidence', async () => {
  const root = mkdtempSync(join(tmpdir(), 'cronos-invalid-envelope-'))
  try {
    writeFileSync(join(root, 'trace.zip.enc'), 'unprotected session data')
    await assert.rejects(sanitizeDirectory(root, [], { key: randomBytes(32), runId: 'run-1' }))
  } finally {
    rmSync(root, { force: true, recursive: true })
  }
})

test('repeated sanitization keeps protected evidence byte-identical', async () => {
  const root = mkdtempSync(join(tmpdir(), 'cronos-sanitize-idempotent-'))
  try {
    const key = randomBytes(32)
    writeFileSync(join(root, 'trace.zip'), Buffer.from('opaque sensitive trace'))
    await sanitizeDirectory(root, [], { key, runId: 'run-1' })
    const afterFirst = readFileSync(join(root, 'trace.zip.enc'))
    await sanitizeDirectory(root, [], { key, runId: 'run-1' })
    assert.deepEqual(readFileSync(join(root, 'trace.zip.enc')), afterFirst)
    assert.equal(recoverEvidence(afterFirst, key, { run_id: 'run-1', path: 'trace.zip' }).toString(), 'opaque sensitive trace')
  } finally {
    rmSync(root, { force: true, recursive: true })
  }
})

test('removes nested Playwright auth-state directories', async () => {
  const root = mkdtempSync(join(tmpdir(), 'cronos-artifact-test-'))
  try {
    const authDirectory = join(root, '.auth')
    mkdirSync(authDirectory)
    writeFileSync(join(authDirectory, 'storage.json'), '{"token":"fake"}\n')

    await sanitizeDirectory(root, [])

    assert.equal(existsSync(authDirectory), false)
  } finally {
    rmSync(root, { force: true, recursive: true })
  }
})

test('removes nested Playwright traces while preserving safe reports and screenshots', async () => {
  const root = mkdtempSync(join(tmpdir(), 'cronos-artifact-test-'))
  try {
    const nested = join(root, 'failure', 'deep')
    mkdirSync(nested, { recursive: true })
    const trace = join(nested, 'trace.zip')
    const screenshot = join(nested, 'screenshot.png')
    const junit = join(nested, 'results.xml')
    writeFileSync(trace, Buffer.from('opaque trace'))
    writeFileSync(screenshot, Buffer.from([0, 1, 2, 3]))
    writeFileSync(junit, '<testsuite tests="1" />\n')

    await sanitizeDirectory(root, [])

    assert.equal(existsSync(trace), false)
    assert.equal(existsSync(screenshot), true)
    assert.equal(readFileSync(screenshot).toString('hex'), '00010203')
    assert.equal(readFileSync(junit, 'utf8'), '<testsuite tests="1" />\n')
  } finally {
    rmSync(root, { force: true, recursive: true })
  }
})

test('resolves the owned and external E2E stack origins explicitly', () => {
  assert.equal(resolveE2eBaseUrl({ baseUrl: 'http://localhost:5174' }), 'http://localhost:5174')
  assert.equal(resolveE2eBaseUrl({ externalStack: true }), 'http://localhost:5173')
  assert.equal(
    resolveE2eBaseUrl({ externalStack: true, baseUrl: 'https://e2e.example.test' }),
    'https://e2e.example.test',
  )
  assert.equal(resolveE2eBaseUrl(), 'http://127.0.0.1:5174')
  const compose = readFileSync(join(ROOT, 'docker-compose.test.yml'), 'utf8')
  assert.ok(compose.includes(`FRONTEND_URL: ${resolveE2eBaseUrl()}`))
  assert.ok(compose.includes(`CLERK_AUTHORIZED_PARTIES: ${resolveE2eBaseUrl()}`))
})

test('uses one E2E base URL in Playwright, setup, helpers and URL-building specs', () => {
  const consumers = [
    'frontend/playwright.config.js',
    'frontend/e2e/global.setup.js',
    'frontend/e2e/utils/clerk-helpers.js',
    'frontend/e2e/utils/fresh-founder.js',
    'frontend/e2e/auth/local-auth-redirects.spec.js',
    'frontend/e2e/auth/login-layout.spec.js',
    'frontend/e2e/auth/onboarding-create-organization.spec.js',
    'frontend/e2e/foundation/first-schedule-approval-dashboard.spec.js',
    'frontend/e2e/scheduler/generation.spec.js',
  ]

  for (const relativePath of consumers) {
    const source = readFileSync(join(ROOT, relativePath), 'utf8')
    assert.match(source, /import \{[^}]*E2E_BASE_URL[^}]*\} from /)
    assert.doesNotMatch(source, /process\.env\.BASE_URL\s*\|\|/)
  }
})

test('keeps the primary failure when cleanup also fails', () => {
  assert.equal(preservePrimaryFailure(1, 3), 1)
  assert.equal(preservePrimaryFailure(0, 3), 3)
  assert.equal(preservePrimaryFailure(7, 3), 7)
})

test('owned cleanup runs every cleaner once and labels every failed cleaner', async () => {
  const calls = []
  const healthy = await cleanupOwnedResources({}, [
    ['clerk', async () => { calls.push('clerk'); return 0 }],
    ['stack', async () => { calls.push('stack'); return 0 }],
  ])
  assert.deepEqual(calls, ['clerk', 'stack'])
  assert.deepEqual(healthy, { code: 0, failures: [] })

  const mixed = await cleanupOwnedResources({}, [
    ['clerk', async () => { calls.push('clerk'); return 3 }],
    ['stack', async () => { calls.push('stack'); return 1 }],
  ])
  assert.deepEqual(calls, ['clerk', 'stack', 'clerk', 'stack'])
  assert.equal(mixed.code, 3)
  assert.deepEqual(mixed.failures, ['clerk: failed (3)', 'stack: failed (1)'])
})

test('a throwing first cleaner never prevents stopping the owned test stack', async () => {
  const calls = []
  const result = await cleanupOwnedResources({}, [
    ['clerk', async () => { calls.push('clerk'); throw undefined }],
    ['stack', async () => { calls.push('stack'); throw new Error('raw provider payload secret') }],
  ])
  assert.deepEqual(calls, ['clerk', 'stack'])
  assert.equal(result.code, 3)
  assert.deepEqual(result.failures, ['clerk: failed (3)', 'stack: failed (3)'])
  assert.equal(JSON.stringify(result.failures).includes('raw provider payload'), false)

  calls.length = 0
  const preserved = await cleanupOwnedResources({}, [
    ['clerk', async () => { calls.push('clerk'); throw null }],
    ['stack', async () => { calls.push('stack'); return 1 }],
  ])
  assert.deepEqual(calls, ['clerk', 'stack'])
  assert.equal(preserved.code, 3)
  assert.deepEqual(preserved.failures, ['clerk: failed (3)', 'stack: failed (1)'])
})

test('the verified result guard fails closed without leaking raw reasons and keeps the primary failure class', async () => {
  const key = randomBytes(32)
  const signingKey = randomBytes(32)
  let verified = 0
  await verifiedResultGuard({ result: {}, artifactRoot: 'root', key, signingKey, verify: async () => { verified += 1 } })
  assert.equal(verified, 1)
  await assert.rejects(
    verifiedResultGuard({ result: {}, artifactRoot: 'root', key, signingKey, verify: async () => { throw new Error('raw secret xyz') } }),
    error => error.runnerCode === 1
      && error.message === 'Signed artifact integrity verification failed'
      && error.cause?.message === 'raw secret xyz'
      && !/raw secret/.test(error.message),
  )
  await assert.rejects(
    verifiedResultGuard({
      result: {}, artifactRoot: 'root', key, signingKey,
      primaryError: Object.assign(new Error('playwright primary'), { runnerCode: 3 }),
      verify: async () => { throw new Error('auxiliary') },
    }),
    error => error.runnerCode === 3,
  )
})

test('refuses resources that are not owned by the current run', () => {
  assert.equal(isOwnedResource('cronos-test-owned', new Set(['cronos-test-owned'])), true)
  assert.equal(isOwnedResource('cronos-dev', new Set(['cronos-test-owned'])), false)
})

test('summarizes structured JUnit cases without parsing terminal output', () => {
  const summary = summarizeJunit(`
    <testsuites><testsuite tests="3">
      <testcase name="ok" />
      <testcase name="failed"><failure /></testcase>
      <testcase name="skipped"><skipped /></testcase>
    </testsuite></testsuites>
  `)
  assert.deepEqual(summary, { collected: 3, passed: 1, failed: 1, skipped: 1, errors: 0 })
})

test('rejects database DDL targets outside the owned test database', () => {
  assert.throws(() => validateDatabaseTargets({
    runtimeUrl: 'postgresql+asyncpg://app:test@127.0.0.1:5432/cronos_test_db',
    migrationUrl: 'postgresql+psycopg2://migrator:test@127.0.0.1:5433/cronos_test_db',
    host: '127.0.0.1',
    port: 5432,
    database: 'cronos_test_db',
  }), /outside the owned test database/)
  assert.throws(() => validateDatabaseTargets({
    runtimeUrl: 'postgresql+asyncpg://app:test@127.0.0.1:5432/cronos_test_db',
    migrationUrl: 'postgresql+psycopg2://migrator:test@127.0.0.1:5432/production',
    host: '127.0.0.1',
    port: 5432,
    database: 'cronos_test_db',
  }), /outside the owned test database/)
})

test('counts nonblank source lines and classifies measured code', () => {
  assert.equal(countNonBlankLines('\nconst value = 1\n  \n'), 1)
  assert.equal(classifyPath('backend/app/services/example.py'), 'backendProduction')
  assert.equal(classifyPath('frontend/src/test/example.test.jsx'), 'frontendTests')
  assert.equal(classifyPath('frontend/e2e/example.spec.js'), 'e2eTests')
  assert.equal(classifyPath('documentation/README.md'), null)
})

test('includes untracked source paths in the measured file set', () => {
  const files = collectFiles('backend/app/new_file.py\nfrontend/src/new_file.jsx\n')
  const measured = measureFiles(
    files,
    (filePath) => filePath.endsWith('.py') ? 'x = 1\n' : 'export const x = 1\n',
    () => true,
  )
  assert.deepEqual(measured.files.map(({ path }) => path), ['backend/app/new_file.py', 'frontend/src/new_file.jsx'])
  assert.deepEqual(measured.counts, {
    backendProduction: 1,
    frontendProduction: 1,
    backendTests: 0,
    frontendTests: 0,
    e2eTests: 0,
  })
})

const preparationKey = randomBytes(32)
const preparationSigningKey = randomBytes(32)

function writeRegistry(directory, name, value) {
  const path = join(directory, name)
  writeFileSync(path, JSON.stringify(signRegistry(value, preparationSigningKey)))
  return path
}

test('preparation orchestration keeps a stage1 protection failure even when stage2 passes', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'cronos-orchestration-'))
  try {
    const { run, registry } = preparationFixture()
    const registryPath = writeRegistry(directory, 'ui-registry.json', registry)
    const calls = []
    const finalizeRunImpl = async (input) => {
      calls.push(input)
      const failures = calls.length === 1
        ? [...input.failures, 'Artifact finalization failed: registries']
        : [...input.failures]
      return {
        run: { ...input, failures, evidence_protected: calls.length > 1 },
        artifacts: calls.length > 1 ? [{ path: 'preparation/persistent-credentials.json.enc' }] : [],
        envelope: calls.length > 1 ? {} : null,
      }
    }
    let retainCalls = 0
    const { result, assessment, prepared } = await finalizePreparation({
      run, artifactRoot: join(directory, 'artifacts'), key: preparationKey, signingKey: preparationSigningKey,
      secrets: [], registryPath, observedReport: run.preparation,
      persistentRegistryPath: join(directory, 'persistent.json'), secretRegistryPath: join(directory, 'secret.json'),
      finalizeRunImpl, retain: async () => { retainCalls += 1 },
    })
    assert.equal(calls.length, 2)
    assert.ok(calls[1].failures.includes('Artifact finalization failed: registries'))
    assert.equal(retainCalls, 0)
    assert.equal(result.run.evidence_protected, true)
    assert.equal(prepared, false)
    assert.ok(assessment.failures.includes('Artifact finalization failed: registries'))
  } finally { rmSync(directory, { recursive: true, force: true }) }
})

function writePreparationArtifacts(directory, { credentials = true } = {}) {
  const artifactRoot = join(directory, 'acceptance-artifacts')
  mkdirSync(join(artifactRoot, 'preparation'), { recursive: true })
  if (credentials) {
    writeFileSync(join(artifactRoot, 'preparation', 'persistent-credentials.json.enc'),
      protectEvidence(Buffer.from('private login credentials'), preparationKey, { run_id: 'run-1', path: 'preparation/persistent-credentials.json' }))
  }
  return artifactRoot
}

test('a real promotion rejection is classified and the signed envelope matches the delivered result', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'cronos-orchestration-'))
  try {
    const { run, registry } = preparationFixture()
    const artifactRoot = writePreparationArtifacts(directory)
    const registryPath = writeRegistry(directory, 'ui-registry.json', registry)
    const persistentRegistryPath = join(directory, 'persistent.json')
    writeFileSync(persistentRegistryPath, JSON.stringify(signRegistry({ schema_version: 1, run_id: 'run-1', organizations: [], history_verified: false }, randomBytes(32))))
    const secretRegistryPath = join(directory, 'secret.json')
    writeFileSync(secretRegistryPath, JSON.stringify(['123456']))
    const { result, assessment, prepared } = await finalizePreparation({
      run, artifactRoot, key: preparationKey, signingKey: preparationSigningKey, secrets: ['123456'],
      registryPath, observedReport: run.preparation, persistentRegistryPath, secretRegistryPath,
    })
    assert.equal(prepared, false)
    assert.equal(assessment.status, 'failed')
    assert.ok(result.run.failures.includes('Persistent school promotion failed'))
    assert.equal(result.run.failures.some(message => /signature|secret-value/.test(message)), false)
    const manifest = await verifyRunArtifacts(result.envelope, artifactRoot, { key: preparationKey, signingKey: preparationSigningKey })
    assert.deepEqual(manifest.run, result.run)
    assert.deepEqual(manifest.assessment, result.assessment)
    assert.ok(manifest.run.failures.includes('Persistent school promotion failed'))
    assert.equal(evaluatePreparation(manifest.run, registry, manifest.artifacts).status, 'failed')
  } finally { rmSync(directory, { recursive: true, force: true }) }
})

test('a stage1 ineligibility stays in the signed run even when stage2 supplies the missing file', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'cronos-orchestration-'))
  try {
    const { run, registry } = preparationFixture()
    const artifactRoot = writePreparationArtifacts(directory, { credentials: false })
    const registryPath = writeRegistry(directory, 'ui-registry.json', registry)
    const persistentRegistryPath = writeRegistry(directory, 'persistent.json', { schema_version: 1, run_id: 'run-1', organizations: [], history_verified: false })
    const secretRegistryPath = join(directory, 'secret.json')
    writeFileSync(secretRegistryPath, JSON.stringify(['123456']))
    let calls = 0
    const finalizeRunImpl = async (input, root, options) => {
      calls += 1
      if (calls === 2) {
        writeFileSync(join(root, 'preparation', 'persistent-credentials.json.enc'),
          protectEvidence(Buffer.from('recovered credentials'), preparationKey, { run_id: 'run-1', path: 'preparation/persistent-credentials.json' }))
      }
      return finalizeRun(input, root, options)
    }
    const { result, assessment, prepared } = await finalizePreparation({
      run, artifactRoot, key: preparationKey, signingKey: preparationSigningKey, secrets: ['123456'],
      registryPath, observedReport: run.preparation, persistentRegistryPath, secretRegistryPath, finalizeRunImpl,
    })
    assert.equal(calls, 2)
    assert.equal(prepared, false)
    assert.equal(assessment.status, 'failed')
    assert.ok(result.run.failures.includes('Protected persistent credentials are missing'))
    const manifest = await verifyRunArtifacts(result.envelope, artifactRoot, { key: preparationKey, signingKey: preparationSigningKey })
    assert.deepEqual(manifest.run, result.run)
    assert.ok(manifest.run.failures.includes('Protected persistent credentials are missing'))
    assert.equal(evaluatePreparation(manifest.run, registry, manifest.artifacts).status, 'failed')
  } finally { rmSync(directory, { recursive: true, force: true }) }
})

test('preparation orchestration delivers a verifiable inventory with both protected registries', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'cronos-orchestration-'))
  try {
    const { run, registry } = preparationFixture()
    const artifactRoot = join(directory, 'acceptance-artifacts')
    mkdirSync(join(artifactRoot, 'preparation'), { recursive: true })
    writeFileSync(join(artifactRoot, 'preparation', 'persistent-credentials.json.enc'),
      protectEvidence(Buffer.from('private login credentials'), preparationKey, { run_id: 'run-1', path: 'preparation/persistent-credentials.json' }))
    const registryPath = writeRegistry(directory, 'ui-registry.json', registry)
    const persistentRegistryPath = writeRegistry(directory, 'persistent.json', { schema_version: 1, run_id: 'run-1', organizations: [], history_verified: false })
    const secretRegistryPath = join(directory, 'secret.json')
    writeFileSync(secretRegistryPath, JSON.stringify(['123456']))
    const { result, assessment, prepared } = await finalizePreparation({
      run, artifactRoot, key: preparationKey, signingKey: preparationSigningKey, secrets: ['123456'],
      registryPath, observedReport: run.preparation, persistentRegistryPath, secretRegistryPath,
    })
    assert.equal(prepared, true)
    assert.equal(assessment.status, 'prepared')
    const manifest = await verifyRunArtifacts(result.envelope, artifactRoot, { key: preparationKey, signingKey: preparationSigningKey })
    assert.deepEqual(manifest.artifacts, result.artifacts)
    const paths = manifest.artifacts.map(item => item.path)
    assert.ok(paths.includes('preparation/persistent-registry.json.enc'))
    assert.ok(paths.includes('preparation/private-secret-registry.json.enc'))
  } finally { rmSync(directory, { recursive: true, force: true }) }
})
