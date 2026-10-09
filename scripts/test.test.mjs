import assert from 'node:assert/strict'
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
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
  displayArgs,
  finalizePreparation,
  isOwnedResource,
  parseArgs,
  preservePrimaryFailure,
  ROOT,
  resolveE2eBaseUrl,
  summarizeJunit,
  validateDatabaseTargets,
} from './test.mjs'
import { redactSecrets, sanitizeDirectory } from './sanitize-test-artifacts.mjs'
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

test('exposes production acceptance as its own command', () => {
  assert.equal(parseArgs(['acceptance']).command, 'acceptance')
  assert.throws(() => parseArgs(['acceptance', '--project', 'acceptance']), /only valid for e2e/)
  assert.throws(() => parseArgs(['acceptance', '--', 'extra']), /not supported/)
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
