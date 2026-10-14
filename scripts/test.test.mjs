import assert from 'node:assert/strict'
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import test from 'node:test'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { spawnSync } from 'node:child_process'
import {
  backendFastArgs,
  childSpec,
  cleanupOwnedResources,
  criticalPytestArgs,
  displayArgs,
  frontendFastArgs,
  frontendJunitEnv,
  isOwnedResource,
  loadE2eEnvFile,
  parseArgs,
  parseCriticalManifest,
  preservePrimaryFailure,
  ROOT,
  resolveE2eBaseUrl,
  runtimeProofFailures,
  summarizeJunit,
  validateDatabaseTargets,
} from './test.mjs'
import { redactSecrets, sanitizeDirectory } from './sanitize-test-artifacts.mjs'
import { classifyPath, collectFiles, countNonBlankLines, measureFiles } from './loc-report.mjs'

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

test('the fast backend run skips the slow solver test unless the caller selects a marker', () => {
  assert.deepEqual(backendFastArgs(), ['-m', 'not slow_solver'])
  assert.deepEqual(backendFastArgs(['-k', 'timesheet']), ['-m', 'not slow_solver', '-k', 'timesheet'])
  assert.deepEqual(backendFastArgs(['-m', 'slow_solver']), ['-m', 'slow_solver'])
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
  assert.doesNotMatch(fast, /test:scripts/, 'the repository script tests belong to e2e-runtime')

  const lines = readFileSync(join(ROOT, '.github/workflows/ci.yml'), 'utf8').split(/\r?\n/)
  const runtimeStart = lines.indexOf('  e2e-runtime:')
  assert.notEqual(runtimeStart, -1, 'the e2e-runtime job must exist')
  const runtimeEnd = lines.findIndex((line, index) => index > runtimeStart && /^  [a-z0-9-]+:$/.test(line))
  const runtime = lines.slice(runtimeStart, runtimeEnd === -1 ? lines.length : runtimeEnd)
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
  const infrastructure = runtime.indexOf('        run: npm run test:scripts')
  assert.ok(
    install !== -1 && install < lint && lint < audit && install < infrastructure,
    'the relocated commands run after the frontend install',
  )
  // The only job condition is the skip for a merge whose pull request head already passed.
  assert.deepEqual(runtime.filter((line) => /^    if:/.test(line)), [
    "    if: ${{ !cancelled() && needs.already-verified.outputs.verified != 'true' }}",
  ], 'the e2e-runtime job runs unless the same tree already passed')
  for (const [label, runLine] of [['frontend lint', lint], ['production dependency audit', audit], ['repository script tests', infrastructure]]) {
    const block = stepBlock(runLine)
    assert.ok(block.includes('        working-directory: frontend'), `${label} runs in the frontend directory`)
    assert.equal(block.some((line) => /^        if:/.test(line)), false, `${label} step must stay unconditional`)
  }
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

test('the sanitizer CLI redacts every configured CI credential from text artifacts', () => {
  const directory = mkdtempSync(join(tmpdir(), 'cronos-cli-sanitize-'))
  try {
    writeFileSync(join(directory, 'report.json'), '{"note":"sk_test_fake and whsec_fake, keep this"}\n')
    const result = spawnSync(process.execPath, [join(ROOT, 'scripts/sanitize-test-artifacts.mjs'), directory], {
      windowsHide: true, encoding: 'utf8',
      env: { ...process.env, CLERK_SECRET_KEY: 'sk_test_fake', CLERK_WEBHOOK_SECRET: 'whsec_fake' },
    })
    assert.equal(result.status, 0, result.stderr)
    assert.equal(readFileSync(join(directory, 'report.json'), 'utf8'), '{"note":"[REDACTED] and [REDACTED], keep this"}\n')
  } finally {
    rmSync(directory, { force: true, recursive: true })
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

test('the shared E2E env file fills only missing Clerk inputs', () => {
  const dir = mkdtempSync(join(tmpdir(), 'cronos-e2e-env-'))
  try {
    const file = join(dir, 'e2e.env')
    writeFileSync(file, [
      '# comment',
      'CLERK_SECRET_KEY=sk_test_file',
      'E2E_CLERK_ADMIN_EMAIL="admin+clerk_test@example.com"',
      'E2E_CLERK_TEACHER_EMAIL=teacher+clerk_test@example.com',
      'DATABASE_URL=postgresql://unrelated',
      '',
    ].join('\n'))
    const env = { E2E_CLERK_TEACHER_EMAIL: 'shell+clerk_test@example.com' }
    assert.equal(loadE2eEnvFile(file, env), true)
    assert.equal(env.CLERK_SECRET_KEY, 'sk_test_file')
    assert.equal(env.E2E_CLERK_ADMIN_EMAIL, 'admin+clerk_test@example.com')
    assert.equal(env.E2E_CLERK_TEACHER_EMAIL, 'shell+clerk_test@example.com')
    assert.equal(env.DATABASE_URL, undefined)
    assert.equal(loadE2eEnvFile(join(dir, 'missing.env'), {}), false)
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
})
