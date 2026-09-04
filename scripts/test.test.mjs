import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { join } from 'node:path'
import {
  childSpec,
  displayArgs,
  isOwnedResource,
  parseArgs,
  planFor,
  preservePrimaryFailure,
  ROOT,
  resolveE2eBaseUrl,
  summarizeJunit,
  validateDatabaseTargets,
} from './test.mjs'

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

test('fast plans never consult Docker or install dependencies implicitly', () => {
  const executables = planFor({ command: 'fast', scope: 'all' }).map((entry) => entry.executable)
  assert.deepEqual(executables, ['python', 'npm'])
})

test('resolves the owned and external E2E stack origins explicitly', () => {
  assert.equal(resolveE2eBaseUrl({ baseUrl: 'http://localhost:5174' }), 'http://localhost:5174')
  assert.equal(resolveE2eBaseUrl({ externalStack: true }), 'http://localhost:5173')
  assert.equal(
    resolveE2eBaseUrl({ externalStack: true, baseUrl: 'https://e2e.example.test' }),
    'https://e2e.example.test',
  )
  assert.equal(resolveE2eBaseUrl(), 'http://localhost:5174')
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
    assert.match(source, /import \{ E2E_BASE_URL \} from /)
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
