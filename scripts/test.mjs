import { createHash, randomBytes } from 'node:crypto'
import { access, mkdir, readFile, writeFile } from 'node:fs/promises'
import os from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'

export const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
export const BACKEND = join(ROOT, 'backend')
export const FRONTEND = join(ROOT, 'frontend')
export const ARTIFACTS = join(ROOT, '.test-artifacts')

const COMPOSE_FILE = join(ROOT, 'docker-compose.test.yml')
const SCOPES = new Set(['backend', 'frontend', 'all'])
const PROFILES = new Set(['fast', 'integration', 'e2e', 'all'])
const E2E_PROJECTS = new Set(['public', 'auth', 'app', 'provider', 'faults'])

export const HELP = `Usage: node scripts/test.mjs <command> [options]

Commands:
  setup --scope backend|frontend|all
  doctor --profile fast|integration|e2e|all
  fast --scope backend|frontend|all [-- runner arguments]
  integration [-- runner arguments]
  e2e [--project public|auth|app|provider|faults]
  all --scope backend|frontend|all
  benchmark --profile fast|integration|e2e|all
`

export function parseArgs(argv) {
  const [command, ...rest] = argv
  if (!command) throw usageError('A command is required.')
  const separator = rest.indexOf('--')
  const options = separator === -1 ? rest : rest.slice(0, separator)
  const forwarded = separator === -1 ? [] : rest.slice(separator + 1)
  const parsed = { command, scope: 'all', profile: 'fast', project: undefined, forwarded }
  let scopeWasProvided = false
  let profileWasProvided = false

  if (!['setup', 'doctor', 'fast', 'integration', 'e2e', 'all', 'benchmark'].includes(command)) {
    throw usageError(`Unknown command: ${command}`)
  }
  if (forwarded.length && !['fast', 'integration'].includes(command)) {
    throw usageError(`Arguments after -- are not supported by ${command}.`)
  }

  for (let index = 0; index < options.length; index += 1) {
    const option = options[index]
    if (!option.startsWith('--')) throw usageError(`Unexpected argument: ${option}`)
    const name = option.slice(2)
    const value = options[index + 1]
    if (!value || value.startsWith('--')) throw usageError(`Option --${name} requires a value.`)
    if (name === 'scope') {
      if (scopeWasProvided) throw usageError('Only one --scope option is allowed.')
      scopeWasProvided = true
      parsed.scope = value
    } else if (name === 'profile') {
      if (profileWasProvided) throw usageError('Only one --profile option is allowed.')
      profileWasProvided = true
      parsed.profile = value
    } else if (name === 'project') {
      if (parsed.project !== undefined) throw usageError('Only one --project option is allowed.')
      parsed.project = value
    } else {
      throw usageError(`Unknown option: --${name}`)
    }
    index += 1
  }

  if (['setup', 'fast', 'all'].includes(command) && !SCOPES.has(parsed.scope)) {
    throw usageError(`Invalid scope: ${parsed.scope}`)
  }
  if (['doctor', 'benchmark'].includes(command) && !PROFILES.has(parsed.profile)) {
    throw usageError(`Invalid profile: ${parsed.profile}`)
  }
  if (command === 'e2e' && parsed.project !== undefined && !E2E_PROJECTS.has(parsed.project)) {
    throw usageError(`Invalid E2E project: ${parsed.project}`)
  }
  if (command !== 'e2e' && parsed.project !== undefined) {
    throw usageError(`--project is only valid for e2e.`)
  }
  return parsed
}

function usageError(message) {
  return Object.assign(new Error(`${message}\n\n${HELP}`), { usage: true })
}

export function preservePrimaryFailure(primaryCode, cleanupCode) {
  return primaryCode !== 0 ? primaryCode : cleanupCode
}

export function isOwnedResource(resourceId, ownedResourceIds) {
  return Boolean(resourceId) && ownedResourceIds.has(resourceId)
}

export function childSpec(executable, args) {
  return { executable, args: [...args] }
}

export function planFor({ command, scope = 'all' }) {
  if (command === 'fast') {
    return scope === 'backend'
      ? [childSpec('python', ['-m', 'pytest', 'tests/unit'])]
      : scope === 'frontend'
        ? [childSpec('npm', ['test'])]
        : [childSpec('python', ['-m', 'pytest', 'tests/unit']), childSpec('npm', ['test'])]
  }
  return []
}

function executable(name) {
  if (process.platform === 'win32' && (name === 'npm' || name === 'npx')) return process.execPath
  return process.platform === 'win32' ? `${name}.exe` : name
}

function nodePackageBin(name) {
  return join(dirname(process.execPath), 'node_modules', 'npm', 'bin', `${name}-cli.js`)
}

function npmSpec(args) {
  return process.platform === 'win32'
    ? childSpec(process.execPath, [nodePackageBin('npm'), ...args])
    : childSpec(executable('npm'), args)
}

function npxSpec(args) {
  return process.platform === 'win32'
    ? childSpec(process.execPath, [nodePackageBin('npx'), ...args])
    : childSpec(executable('npx'), args)
}

function localPython() {
  const suffix = process.platform === 'win32' ? join('Scripts', 'python.exe') : join('bin', 'python')
  return join(BACKEND, '.venv', suffix)
}

function baseTestEnvironment(overrides = {}) {
  return {
    ...process.env,
    ENVIRONMENT: 'local',
    DATABASE_URL: 'postgresql+asyncpg://cronos_app:test@127.0.0.1:5432/cronos_test_db',
    MIGRATION_DATABASE_URL: 'postgresql+psycopg2://cronos_migrator:test@127.0.0.1:5432/cronos_test_db',
    TEST_DATABASE_URL: 'postgresql+asyncpg://cronos_app:test@127.0.0.1:5432/cronos_test_db',
    REDIS_URL: 'redis://127.0.0.1:9/0',
    CELERY_BROKER_URL: 'redis://127.0.0.1:9/0',
    DATABASE_POOLING_ENABLED: 'false',
    RATELIMIT_ENABLED: 'false',
    SENTRY_DSN: '',
    PYTHONPATH: BACKEND,
    ...overrides,
  }
}

async function spawnProcess(spec, { cwd = ROOT, env = process.env, capture = false, label } = {}) {
  const startedAt = Date.now()
  if (label) console.log(`[test] ${label}: ${spec.executable} ${spec.args.join(' ')}`)
  const child = spawn(spec.executable, spec.args, {
    cwd,
    env,
    shell: false,
    stdio: capture ? ['ignore', 'pipe', 'pipe'] : 'inherit',
    windowsHide: true,
  })
  let stdout = ''
  let stderr = ''
  if (capture) {
    child.stdout.on('data', (chunk) => { stdout += chunk })
    child.stderr.on('data', (chunk) => { stderr += chunk })
  }
  const result = await new Promise((resolveResult, reject) => {
    child.once('error', reject)
    child.once('close', (code, signal) => resolveResult({ code: code ?? 1, signal, stdout, stderr }))
  })
  const durationMs = Date.now() - startedAt
  if (label) console.log(`[test] ${label}: exit ${result.code} in ${durationMs}ms`)
  return { ...result, durationMs }
}

async function runChecked(spec, options = {}) {
  const result = await spawnProcess(spec, options)
  if (result.code !== 0) {
    const error = new Error(`${options.label || spec.executable} failed with exit code ${result.code}`)
    error.exitCode = result.code
    error.runnerCode = options.environmentFailure ? 3 : 1
    error.result = result
    throw error
  }
  return result
}

async function runCapture(spec, options = {}) {
  const result = await spawnProcess(spec, { ...options, capture: true })
  if (result.code !== 0) {
    const error = new Error(`${options.label || spec.executable} failed with exit code ${result.code}`)
    error.exitCode = result.code
    error.runnerCode = 3
    error.result = result
    throw error
  }
  return result.stdout.trim()
}

async function sha256(path) {
  return createHash('sha256').update(await readFile(path)).digest('hex')
}

async function setupBackend(context) {
  const python = executable('python')
  if (!(await access(localPython()).then(() => true).catch(() => false))) {
    await runChecked(childSpec(python, ['-m', 'venv', join(BACKEND, '.venv')]), {
      label: 'create backend virtualenv', environmentFailure: true,
    })
  }
  const venvPython = localPython()
  await runChecked(childSpec(venvPython, ['-m', 'pip', 'install', '--require-hashes', '-r', 'requirements-dev.txt']), {
    cwd: BACKEND, label: 'install backend locked dependencies', environmentFailure: true,
  })
  context.prepared.backend = true
}

async function setupFrontend(context) {
  await runChecked(npmSpec(['ci', '--ignore-scripts']), {
    cwd: FRONTEND, label: 'install frontend locked dependencies', environmentFailure: true,
  })
  await runChecked(npxSpec(['--no-install', 'playwright', 'install', 'chromium']), {
    cwd: FRONTEND, label: 'install Playwright Chromium', environmentFailure: true,
  })
  context.prepared.frontend = true
}

async function runSetup(scope, context) {
  if (scope === 'backend' || scope === 'all') await setupBackend(context)
  if (scope === 'frontend' || scope === 'all') await setupFrontend(context)
  await writeSetupState(context)
}

async function writeSetupState(context) {
  const state = {
    revision: context.revision,
    preparedAt: new Date().toISOString(),
    lockfiles: {
      backend: await sha256(join(BACKEND, 'requirements-dev.txt')),
      frontend: await sha256(join(FRONTEND, 'package-lock.json')),
    },
  }
  await writeFile(join(context.artifactDir, 'setup-state.json'), `${JSON.stringify(state, null, 2)}\n`)
}

async function checkVersion(spec, expected, label) {
  try {
    const output = await runCapture(spec, { label })
    const match = output.match(/(\d+)(?:\.(\d+))?(?:\.(\d+))?/)
    const actual = match ? match.slice(1, 4).filter(Boolean).join('.') : 'unknown'
    if (!match || !expected.test(actual)) return `${label}: found ${actual}; expected ${expected.source}.`
  } catch (error) {
    return `${label}: executable unavailable; ${error.message}`
  }
  return null
}

async function runDoctor(profile, context) {
  const errors = []
  if (profile === 'fast' || profile === 'all') {
    errors.push(await checkVersion(childSpec(process.execPath, ['--version']), /^24\./, 'Node.js'))
    errors.push(await checkVersion(childSpec(executable('python'), ['--version']), /^3\.12\./, 'Python'))
    errors.push(await checkVersion(npmSpec(['--version']), /^11\./, 'npm'))
    if (!(await access(localPython()).then(() => true).catch(() => false))) {
      errors.push('Backend virtualenv is missing; run node scripts/test.mjs setup --scope backend.')
    }
    if (!(await access(join(FRONTEND, 'node_modules')).then(() => true).catch(() => false))) {
      errors.push('Frontend dependencies are missing; run node scripts/test.mjs setup --scope frontend.')
    }
  }
  if (profile === 'integration' || profile === 'e2e' || profile === 'all') {
    errors.push(await checkVersion(childSpec(executable('docker'), ['--version']), /^29\./, 'Docker'))
    errors.push(await checkVersion(childSpec(executable('docker'), ['compose', 'version']), /^5\./, 'Docker Compose'))
  }
  const meaningfulErrors = errors.filter(Boolean)
  if (meaningfulErrors.length) {
    meaningfulErrors.forEach((error) => console.error(`[doctor] ${error}`))
    const failure = new Error('Doctor found invalid environment.')
    failure.runnerCode = 3
    throw failure
  }
  context.doctor = profile
  console.log(`[doctor] ${profile}: ok`)
}

function backendCommand(args, overrides = {}) {
  return {
    spec: childSpec(localPython(), ['-m', 'pytest', '-c', join(BACKEND, 'pyproject.toml'), ...args]),
    options: { cwd: ROOT, env: baseTestEnvironment(overrides) },
  }
}

async function runBackendTests(paths, forwarded = [], overrides = {}) {
  const { spec, options } = backendCommand([...paths, ...forwarded], overrides)
  return runChecked(spec, { ...options, label: `pytest ${paths.join(' ')}` })
}

async function runFrontendTests(args, label, env = {}) {
  return runChecked(npmSpec(args), {
    cwd: FRONTEND,
    env: { ...process.env, VITE_API_BASE_URL: '/api/v1', ...env },
    label,
  })
}

async function runFast(scope, forwarded) {
  if (scope === 'backend' || scope === 'all') {
    await runBackendTests([
      join(BACKEND, 'tests', 'unit'),
      '--disable-socket',
      '--allow-hosts=127.0.0.1,localhost',
    ], forwarded, { RATELIMIT_ENABLED: 'false' })
  }
  if (scope === 'frontend' || scope === 'all') {
    await runFrontendTests(['test', '--', '--project=node', '--project=dom', ...forwarded], 'Vitest fast')
  }
}

function composeSpec(args) {
  return childSpec(executable('docker'), ['compose', '-f', COMPOSE_FILE, '-p', args.project, ...args.rest])
}

async function startTestStack(context) {
  const token = `${Date.now()}-${process.pid}-${randomBytes(4).toString('hex')}`
  const project = `cronos-test-${token}`
  const postgresPassword = randomBytes(24).toString('hex')
  const migratorPassword = randomBytes(24).toString('hex')
  const appPassword = randomBytes(24).toString('hex')
  const composeEnv = {
    ...process.env,
    COMPOSE_PROJECT_NAME: project,
    POSTGRES_PASSWORD: postgresPassword,
    CRONOS_MIGRATOR_PASSWORD: migratorPassword,
    CRONOS_APP_PASSWORD: appPassword,
  }
  const compose = (rest) => composeSpec({ project, rest })
  const stack = {
    project,
    composeEnv,
    started: true,
    ownedResourceIds: new Set([project]),
  }
  context.stack = stack
  await runChecked(compose(['up', '-d', '--wait', 'db', 'redis']), {
    env: composeEnv, label: 'start test PostgreSQL and Redis', environmentFailure: true,
  })
  const dbPortOutput = await runCapture(compose(['port', 'db', '5432']), {
    env: composeEnv, label: 'read test PostgreSQL port',
  })
  const redisPortOutput = await runCapture(compose(['port', 'redis', '6379']), {
    env: composeEnv, label: 'read test Redis port',
  })
  const dbPort = Number(dbPortOutput.match(/:(\d+)\s*$/)?.[1])
  const redisPort = Number(redisPortOutput.match(/:(\d+)\s*$/)?.[1])
  if (!dbPort || !redisPort) throw Object.assign(new Error('Test stack did not publish loopback ports.'), { runnerCode: 3 })

  const psql = (database, sql) => composeSpec({
    project,
    rest: ['exec', '-T', '-e', `PGPASSWORD=${postgresPassword}`, 'db', 'psql', '-v', 'ON_ERROR_STOP=1', '-U', 'postgres', '-d', database, '-c', sql],
  })
  const rolesSql = `DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'cronos_migrator') THEN
      CREATE ROLE cronos_migrator LOGIN NOSUPERUSER BYPASSRLS PASSWORD '${migratorPassword}';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'cronos_app') THEN
      CREATE ROLE cronos_app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '${appPassword}';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'cronos_auth_definer') THEN
      CREATE ROLE cronos_auth_definer NOLOGIN NOSUPERUSER BYPASSRLS;
    END IF;
  END $$;
  GRANT cronos_auth_definer TO cronos_migrator;
  ALTER DATABASE cronos_test_db OWNER TO cronos_migrator;
  GRANT CONNECT ON DATABASE cronos_test_db TO cronos_app;`
  await runChecked(psql('cronos_test_db', rolesSql), {
    env: composeEnv, label: 'provision test database roles', environmentFailure: true,
  })
  for (const database of ['cronos_test_gw0', 'cronos_test_gw1']) {
    await runChecked(psql('postgres', `CREATE DATABASE ${database} OWNER cronos_migrator;`), {
      env: composeEnv, label: `create ${database}`, environmentFailure: true,
    })
    await runChecked(psql('postgres', `GRANT CONNECT ON DATABASE ${database} TO cronos_app;`), {
      env: composeEnv, label: `grant ${database} access`, environmentFailure: true,
    })
  }

  Object.assign(stack, {
    dbPort,
    redisPort,
    env: baseTestEnvironment({
      DATABASE_URL: `postgresql+asyncpg://cronos_app:${appPassword}@127.0.0.1:${dbPort}/cronos_test_db`,
      MIGRATION_DATABASE_URL: `postgresql+psycopg2://cronos_migrator:${migratorPassword}@127.0.0.1:${dbPort}/cronos_test_db`,
      TEST_DATABASE_URL: `postgresql+asyncpg://cronos_app:${appPassword}@127.0.0.1:${dbPort}/cronos_test_db`,
      REDIS_URL: `redis://127.0.0.1:${redisPort}/0`,
      CELERY_BROKER_URL: `redis://127.0.0.1:${redisPort}/0`,
    }),
  })
  await writeFile(join(context.artifactDir, 'stack.json'), `${JSON.stringify({
    runId: context.runId, project, dbPort, redisPort, databases: ['cronos_test_db', 'cronos_test_gw0', 'cronos_test_gw1'],
  }, null, 2)}\n`)
  context.stack = stack
  return stack
}

async function stopTestStack(context) {
  const stack = context.stack
  if (!stack?.started || !isOwnedResource(stack.project, stack.ownedResourceIds)) return 0
  const result = await spawnProcess(composeSpec({
    project: stack.project,
    rest: ['down', '--volumes', '--remove-orphans'],
  }), { env: stack.composeEnv, label: 'cleanup owned test stack' })
  stack.started = false
  return result.code
}

async function runIntegration(forwarded = [], context, { coverage = false } = {}) {
  const stack = await startTestStack(context)
  try {
    const prefix = coverage
      ? ['-m', 'pytest', '--cov=app', '--cov-branch', '--cov-report=', '--cov-fail-under=0', '--cov-append']
      : ['-m', 'pytest']
    const integrationArgs = [...prefix, '-c', join(BACKEND, 'pyproject.toml'), join(BACKEND, 'tests', 'integration'), '-n', '2', '--dist=loadscope', ...forwarded]
    await runChecked(childSpec(localPython(), integrationArgs), {
      cwd: BACKEND, env: stack.env, label: 'backend integration tests',
    })
    const contractPrefix = coverage
      ? ['-m', 'pytest', '--cov=app', '--cov-branch', '--cov-report=', '--cov-fail-under=0', '--cov-append']
      : ['-m', 'pytest']
    await runChecked(childSpec(localPython(), [...contractPrefix, '-c', join(BACKEND, 'pyproject.toml'), join(BACKEND, 'tests', 'contracts')]), {
      cwd: BACKEND, env: stack.env, label: 'backend infrastructure contracts',
    })
  } finally {
    context.stack = stack
  }
}

async function runE2e(project, context) {
  const args = ['run', 'test:e2e', '--']
  if (project) args.push('--project', project)
  await runFrontendTests(args, `Playwright ${project || 'all'}`, {
    CI: process.env.CI || 'true',
    PLAYWRIGHT_SKIP_WEB_SERVER: process.env.PLAYWRIGHT_SKIP_WEB_SERVER || '0',
  })
  context.e2e = project || 'all'
}

async function runAllBackend(context) {
  await runChecked(childSpec(localPython(), ['-m', 'ruff', 'format', '--check', BACKEND]), {
    cwd: ROOT, env: baseTestEnvironment(), label: 'Ruff format check',
  })
  await runChecked(childSpec(localPython(), ['-m', 'ruff', 'check', BACKEND]), {
    cwd: ROOT, env: baseTestEnvironment(), label: 'Ruff lint',
  })
  await runChecked(childSpec(localPython(), [
    '-m', 'pytest', '--cov=app', '--cov-branch', '--cov-report=', '--cov-fail-under=0',
    '-c', join(BACKEND, 'pyproject.toml'), join(BACKEND, 'tests', 'unit'),
    '--disable-socket', '--allow-hosts=127.0.0.1,localhost',
  ]), {
    cwd: BACKEND, env: baseTestEnvironment(), label: 'backend unit tests with coverage',
  })
  await runIntegration([], context, { coverage: true })
  await runChecked(childSpec(localPython(), ['-m', 'coverage', 'report', '--fail-under=70']), {
    cwd: BACKEND, env: baseTestEnvironment(), label: 'backend coverage gate',
  })
  await runChecked(childSpec(localPython(), [
    '-m', 'coverage', 'report',
    '--include=app/scheduler/domain/constraints.py,app/scheduler/domain/validation.py',
    '--fail-under=100',
  ]), {
    cwd: BACKEND, env: baseTestEnvironment(), label: 'scheduler coverage gate',
  })
}

async function runAllFrontend() {
  await runFrontendTests(['run', 'lint'], 'ESLint')
  await runFrontendTests(['run', 'lint:dead-code'], 'Knip')
  await runFrontendTests(['run', 'lint:dead-code:production'], 'Knip production')
  await runFrontendTests(['run', 'test:marketing-build'], 'Node script tests')
  await runFrontendTests(['run', 'test:marketing-assets'], 'Asset audit')
  await runFrontendTests(['run', 'test:coverage'], 'Vitest coverage')
  await runFrontendTests(['run', 'build'], 'Frontend build')
  await runFrontendTests(['run', 'audit:production'], 'Production dependency audit')
}

async function runAll(scope, context) {
  if (scope === 'backend' || scope === 'all') await runAllBackend(context)
  if (scope === 'frontend' || scope === 'all') await runAllFrontend()
}

async function runBenchmark(profile, context) {
  const samples = []
  for (let sample = 0; sample < 6; sample += 1) {
    const warmup = sample === 0
    const startedAt = Date.now()
    let exitCode = 0
    try {
      if (profile === 'fast') await runFast('all', [])
      else if (profile === 'integration') await runIntegration([], context)
      else if (profile === 'e2e') await runE2e(undefined, context)
      else await runAll('all', context)
    } catch (error) {
      exitCode = error.runnerCode || 1
      if (!warmup) console.error(`[benchmark] sample ${sample}: ${error.message}`)
    } finally {
      try {
        await stopTestStack(context)
      } catch (error) {
        console.error(`[benchmark] cleanup failed: ${error.message}`)
        exitCode = exitCode || 3
      }
    }
    if (!warmup) samples.push({
      revision: context.revision,
      profile,
      scope: 'all',
      sample,
      cache_state: 'warm',
      workers: profile === 'integration' ? 2 : profile === 'e2e' ? 1 : 2,
      duration_ms: Date.now() - startedAt,
      setup_ms: 0,
      tests_passed: null,
      tests_failed: exitCode === 0 ? 0 : null,
      tests_skipped: null,
      exit_code: exitCode,
    })
  }
  await writeFile(join(context.artifactDir, `benchmark-${profile}.json`), `${JSON.stringify(samples, null, 2)}\n`)
  if (samples.some((sample) => sample.exit_code !== 0)) {
    throw Object.assign(new Error(`Benchmark ${profile} has failed samples.`), { runnerCode: 1 })
  }
}

async function currentRevision() {
  try {
    return (await runCapture(childSpec(executable('git'), ['rev-parse', 'HEAD']), { label: 'read revision' })) || 'unknown'
  } catch {
    return 'unknown'
  }
}

export async function main(argv = process.argv.slice(2)) {
  let parsed
  try {
    parsed = parseArgs(argv)
  } catch (error) {
    console.error(error.message)
    return error.usage ? 2 : 1
  }
  const runId = `${Date.now()}-${process.pid}`
  const artifactDir = join(ARTIFACTS, runId)
  await mkdir(artifactDir, { recursive: true })
  const context = { runId, artifactDir, revision: await currentRevision(), prepared: {} }
  let primaryCode = 0
  try {
    if (parsed.command === 'setup') await runSetup(parsed.scope, context)
    else if (parsed.command === 'doctor') await runDoctor(parsed.profile, context)
    else if (parsed.command === 'fast') await runFast(parsed.scope, parsed.forwarded)
    else if (parsed.command === 'integration') await runIntegration(parsed.forwarded, context)
    else if (parsed.command === 'e2e') await runE2e(parsed.project, context)
    else if (parsed.command === 'all') await runAll(parsed.scope, context)
    else if (parsed.command === 'benchmark') await runBenchmark(parsed.profile, context)
  } catch (error) {
    primaryCode = error.runnerCode || 1
    console.error(`[test] ${error.message}`)
    if (error.result?.stderr) console.error(error.result.stderr)
  }
  let cleanupCode = 0
  try {
    cleanupCode = await stopTestStack(context)
  } catch (error) {
    cleanupCode = 3
    console.error(`[test] cleanup failed: ${error.message}`)
  }
  const exitCode = preservePrimaryFailure(primaryCode, cleanupCode ? 3 : 0)
  await writeFile(join(artifactDir, 'run.json'), `${JSON.stringify({
    revision: context.revision,
    command: parsed.command,
    scope: parsed.scope,
    profile: parsed.profile,
    project: parsed.project ?? null,
    exit_code: exitCode,
    cleanup_exit_code: cleanupCode,
  }, null, 2)}\n`)
  return exitCode
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().then((code) => { process.exitCode = code }).catch((error) => {
    console.error(error)
    process.exitCode = 3
  })
}
