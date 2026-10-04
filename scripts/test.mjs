import { createHash, randomBytes } from 'node:crypto'
import { access, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import net from 'node:net'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'
import { performance } from 'node:perf_hooks'

export const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
export const BACKEND = join(ROOT, 'backend')
export const FRONTEND = join(ROOT, 'frontend')
export const ARTIFACTS = join(ROOT, '.test-artifacts')

const COMPOSE_FILE = join(ROOT, 'docker-compose.test.yml')
const BACKEND_TEST_IMAGE = 'cronos-backend-test:local'
const DOCKER_BACKEND = process.platform === 'win32'
const SCOPES = new Set(['backend', 'frontend', 'all'])
const PROFILES = new Set(['fast', 'integration', 'e2e', 'all'])
const E2E_PROJECTS = new Set(['public', 'auth', 'app', 'provider', 'faults', 'capacity'])
export const INTEGRATION_WORKERS = 4
export const E2E_WORKERS = 2
export const E2E_PORT = 5174

export function resolveE2eBaseUrl({ externalStack = false, baseUrl } = {}) {
  return baseUrl || (externalStack ? 'http://localhost:5173' : `http://127.0.0.1:${E2E_PORT}`)
}

export const HELP = `Usage: node scripts/test.mjs <command> [options]

Commands:
  setup --scope backend|frontend|all
  doctor --profile fast|integration|e2e|all
  fast --scope backend|frontend|all [-- runner arguments]
  integration [-- runner arguments]
  e2e [--project public|auth|app|provider|faults|capacity]
  capacity
  capacity-smoke
  all --scope backend|frontend|all
  benchmark --profile fast|integration|e2e|all [--scope backend|frontend|all]
  campaign [--manifest <path>] [--out <dir>] [--case <id>]... [--mode witness|generator|repair|trajectory|longitudinal] [--time-limit <s>] [--workers <n>] [--resume]
`

export function parseArgs(argv) {
  const [command, ...rest] = argv
  if (!command) throw usageError('A command is required.')
  const separator = rest.indexOf('--')
  const options = separator === -1 ? rest : rest.slice(0, separator)
  const forwarded = separator === -1 ? [] : rest.slice(separator + 1)
  const parsed = {
    command,
    scope: 'all',
    profile: command === 'integration' ? 'integration'
      : command === 'e2e' ? 'e2e'
        : command === 'all' ? 'all'
          : 'fast',
    project: undefined,
    manifest: undefined,
    out: undefined,
    caseIds: [],
    mode: 'witness',
    timeLimit: undefined,
    workers: undefined,
    resume: false,
    forwarded,
  }
  let scopeWasProvided = false
  let profileWasProvided = false

  if (!['setup', 'doctor', 'fast', 'integration', 'e2e', 'capacity', 'capacity-smoke', 'all', 'benchmark', 'campaign'].includes(command)) {
    throw usageError(`Unknown command: ${command}`)
  }
  if (forwarded.length && !['fast', 'integration'].includes(command)) {
    throw usageError(`Arguments after -- are not supported by ${command}.`)
  }

  for (let index = 0; index < options.length; index += 1) {
    const option = options[index]
    if (!option.startsWith('--')) throw usageError(`Unexpected argument: ${option}`)
    const name = option.slice(2)
    if (name === 'resume') {
      parsed.resume = true
      continue
    }
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
    } else if (name === 'manifest') {
      parsed.manifest = value
    } else if (name === 'out') {
      parsed.out = value
    } else if (name === 'case') {
      parsed.caseIds.push(value)
    } else if (name === 'mode') {
      if (!['witness', 'generator', 'repair', 'trajectory', 'longitudinal'].includes(value)) throw usageError(`Invalid campaign mode: ${value}`)
      parsed.mode = value
    } else if (name === 'time-limit') {
      if (!Number.isFinite(Number(value)) || Number(value) <= 0) throw usageError(`Invalid time limit: ${value}`)
      parsed.timeLimit = value
    } else if (name === 'workers') {
      if (!Number.isInteger(Number(value)) || Number(value) < 1) throw usageError(`Invalid worker count: ${value}`)
      parsed.workers = value
    } else {
      throw usageError(`Unknown option: --${name}`)
    }
    index += 1
  }

  if (command === 'campaign' && (scopeWasProvided || profileWasProvided)) {
    throw usageError('--scope and --profile are not valid for campaign.')
  }
  if (
    command !== 'campaign'
    && (
      parsed.manifest !== undefined
      || parsed.out !== undefined
      || parsed.caseIds.length
      || parsed.mode !== 'witness'
      || parsed.timeLimit !== undefined
      || parsed.workers !== undefined
      || parsed.resume
    )
  ) {
    throw usageError('campaign options are only valid for campaign.')
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
  if (command === 'benchmark' && parsed.profile !== 'fast' && scopeWasProvided) {
    throw usageError(`--scope is only valid for benchmark --profile fast.`)
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

function monotonicMs() {
  return performance.now()
}

export function displayArgs(args) {
  return args.map((arg, index) => {
    if (index > 0 && args[index - 1] === '-e' && /(?:PASSWORD|SECRET|TOKEN|COOKIE|STORAGE_STATE)/i.test(arg)) {
      return `${arg.split('=', 1)[0]}=[redacted]`
    }
    return arg
      .replace(/((?:PASSWORD|SECRET|TOKEN|COOKIE|STORAGE_STATE)=)[^\s]*/gi, '$1[redacted]')
      .replace(/(PASSWORD\s+['"])[^'"]+(['"])/gi, '$1[redacted]$2')
      .replace(/(postgres(?:ql)?(?:\+[^:]+)?:\/\/[^:]+:)[^@\s]+(@)/gi, '$1[redacted]$2')
  }).join(' ')
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

function backendPythonSpec(args, env, context, stack = null) {
  if (!DOCKER_BACKEND) return childSpec(localPython(), args)
  const containerPath = (value) => value
    .replaceAll(context.artifactDir, '/artifacts')
    .replaceAll(ROOT, '/workspace')
    .replaceAll('\\', '/')
  const containerEnv = {
    ENVIRONMENT: env.ENVIRONMENT,
    DATABASE_URL: env.DATABASE_URL,
    MIGRATION_DATABASE_URL: env.MIGRATION_DATABASE_URL,
    TEST_DATABASE_URL: env.TEST_DATABASE_URL,
    REDIS_URL: env.REDIS_URL,
    CELERY_BROKER_URL: env.CELERY_BROKER_URL,
    DATABASE_POOLING_ENABLED: env.DATABASE_POOLING_ENABLED,
    RATELIMIT_ENABLED: env.RATELIMIT_ENABLED,
    PYTHONPATH: '/workspace/backend',
  }
  if (stack) {
    for (const key of ['DATABASE_URL', 'MIGRATION_DATABASE_URL', 'TEST_DATABASE_URL']) {
      containerEnv[key] = containerEnv[key].replace(`127.0.0.1:${stack.dbPort}`, 'db:5432')
    }
    for (const key of ['REDIS_URL', 'CELERY_BROKER_URL']) {
      containerEnv[key] = containerEnv[key].replace(`127.0.0.1:${stack.redisPort}`, 'redis:6379')
    }
  }
  return childSpec(executable('docker'), [
    'run', '--rm',
    ...(stack ? ['--network', `${stack.project}_default`] : []),
    '--mount', `type=bind,source=${ROOT},target=/workspace`,
    '--mount', `type=bind,source=${context.artifactDir},target=/artifacts`,
    '-w', '/workspace/backend',
    ...Object.entries(containerEnv).flatMap(([key, value]) => ['-e', `${key}=${value}`]),
    BACKEND_TEST_IMAGE, 'python', ...args.map(containerPath),
  ])
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
    PYTHONPATH: BACKEND,
    ...overrides,
  }
}

async function spawnProcess(spec, { cwd = ROOT, env = process.env, capture = false, label } = {}) {
  const startedAt = monotonicMs()
  if (label) console.log(`[test] ${label}: ${spec.executable} ${displayArgs(spec.args)}`)
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
  const durationMs = Math.round(monotonicMs() - startedAt)
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

function emptyCounts() {
  return {
    collected: null,
    passed: null,
    failed: null,
    skipped: null,
    errors: null,
  }
}

export function summarizeJunit(xml) {
  const cases = [...xml.matchAll(/<testcase\b[\s\S]*?(?:<\/testcase>|\/>)/g)].map(
    ([match]) => match,
  )
  if (!cases.length) return emptyCounts()
  const failed = cases.filter((testCase) => /<(?:failure|error)\b/.test(testCase)).length
  const skipped = cases.filter((testCase) => /<skipped\b/.test(testCase)).length
  const errors = cases.filter((testCase) => /<error\b/.test(testCase)).length
  return {
    collected: cases.length,
    passed: cases.length - failed - skipped,
    failed,
    skipped,
    errors,
  }
}

async function readJunitSummary(reportPath) {
  if (!reportPath || !(await access(reportPath).then(() => true).catch(() => false))) {
    return emptyCounts()
  }
  return summarizeJunit(await readFile(reportPath, 'utf8'))
}

function addPhaseTime(context, phase, durationMs) {
  if (!context || durationMs == null) return
  context.timings[phase] = (context.timings[phase] ?? 0) + durationMs
}

async function runRecorded(spec, options, context, metadata = {}) {
  const startedAt = monotonicMs()
  let result
  try {
    result = await runChecked(spec, options)
    return result
  } catch (error) {
    result = error.result
    throw error
  } finally {
    const durationMs = result?.durationMs ?? Math.round(monotonicMs() - startedAt)
    addPhaseTime(context, metadata.phase || 'tests_ms', durationMs)
    if (context && metadata.name) {
      const counts = await readJunitSummary(metadata.reportPath)
      context.suites.push({
        name: metadata.name,
        kind: metadata.kind || 'tests',
        report: metadata.reportPath ? metadata.reportPath.slice(ROOT.length + 1) : null,
        duration_ms: durationMs,
        workers: metadata.workers ?? null,
        ...counts,
      })
    }
  }
}

async function sha256(path) {
  return createHash('sha256').update(await readFile(path)).digest('hex')
}

async function setupBackend(context) {
  if (DOCKER_BACKEND) {
    await runChecked(childSpec(executable('docker'), [
      'build', '--target', 'ci', '-t', BACKEND_TEST_IMAGE, BACKEND,
    ]), { label: 'build locked backend test image', environmentFailure: true })
    context.prepared.backend = true
    return
  }
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
  const startedAt = monotonicMs()
  if (scope === 'backend' || scope === 'all') await setupBackend(context)
  if (scope === 'frontend' || scope === 'all') await setupFrontend(context)
  addPhaseTime(context, 'preparation_ms', Math.round(monotonicMs() - startedAt))
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
    errors.push(await checkVersion(DOCKER_BACKEND
      ? childSpec(executable('docker'), ['run', '--rm', BACKEND_TEST_IMAGE, 'python', '--version'])
      : childSpec(executable('python'), ['--version']), /^3\.14\./, 'Python'))
    errors.push(await checkVersion(npmSpec(['--version']), /^11\./, 'npm'))
    if (!DOCKER_BACKEND && !(await access(localPython()).then(() => true).catch(() => false))) {
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
  if (profile === 'e2e' || profile === 'all') {
    try {
      validateE2eEnvironment()
    } catch (error) {
      errors.push(error.message)
    }
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

function backendCommand(args, overrides, context) {
  const env = baseTestEnvironment(overrides)
  return {
    spec: backendPythonSpec(['-m', 'pytest', '-c', join(BACKEND, 'pyproject.toml'), ...args], env, context),
    options: { cwd: ROOT, env },
  }
}

async function runBackendTests(paths, forwarded = [], overrides = {}, context, name = 'backend-unit') {
  const reportPath = join(context.artifactDir, `${name}.xml`)
  const { spec, options } = backendCommand([...paths, ...forwarded, `--junitxml=${reportPath}`], overrides, context)
  return runRecorded(spec, { ...options, label: `pytest ${paths.join(' ')}` }, context, {
    name,
    kind: 'pytest',
    reportPath,
    workers: name === 'backend-integration' ? INTEGRATION_WORKERS : 1,
  })
}

async function runFrontendTests(
  args,
  label,
  env = {},
  context,
  name = label.toLowerCase().replaceAll(' ', '-'),
  phase = 'tests_ms',
) {
  const reportPath = context ? join(context.artifactDir, `${name}.xml`) : null
  const testEnv = {
    ...process.env,
    VITE_API_BASE_URL: '/api/v1',
    ...(reportPath ? { VITEST_JUNIT_OUTPUT_FILE: reportPath } : {}),
    ...env,
  }
  return runRecorded(npmSpec(args), {
    cwd: FRONTEND,
    env: testEnv,
    label,
  }, context, context ? {
    name,
    kind: 'vitest',
    reportPath,
    phase,
  } : {})
}

async function runFast(scope, forwarded, context) {
  if (scope === 'backend' || scope === 'all') {
    await runBackendTests([
      join(BACKEND, 'tests', 'unit'),
      '--disable-socket',
      '--allow-hosts=127.0.0.1,localhost',
    ], forwarded, { RATELIMIT_ENABLED: 'false' }, context, 'backend-unit')
  }
  if (scope === 'frontend' || scope === 'all') {
    await runFrontendTests(
      ['test', '--', '--project=node', '--project=dom', ...forwarded],
      'Vitest fast',
      {},
      context,
      'frontend-fast',
    )
  }
}

async function runCampaign(parsed, context) {
  const manifestPath = resolve(parsed.manifest ?? join(BACKEND, 'tests', 'scheduler_lab', 'manifest.json'))
  const outDir = resolve(parsed.out ?? join(context.artifactDir, 'scheduler-lab'))
  const env = baseTestEnvironment({ RATELIMIT_ENABLED: 'false' })
  const codeIdentity = `${context.revision.slice(0, 12)}+${context.git.tree?.slice(0, 12) ?? 'unknown'}`
  const args = [
    '-m', 'app.scheduler.lab.campaign',
    '--manifest', manifestPath,
    '--out', outDir,
    '--commit', context.revision,
    '--code-identity', codeIdentity,
    '--policy-version', 'quality-v1',
    '--mode', parsed.mode,
  ]
  for (const caseId of parsed.caseIds) args.push('--case', caseId)
  if (parsed.timeLimit !== undefined) args.push('--time-limit', parsed.timeLimit)
  if (parsed.workers !== undefined) args.push('--workers', parsed.workers)
  if (parsed.resume) args.push('--resume')
  await runRecorded(backendPythonSpec(args, env, context), {
    cwd: BACKEND, env, label: 'scheduler lab campaign',
  }, context, { name: 'scheduler-campaign', kind: 'campaign' })
}

function composeSpec(args) {
  return childSpec(executable('docker'), ['compose', '-f', COMPOSE_FILE, '-p', args.project, ...args.rest])
}

function ensureTestEmail(value, name) {
  if (!value || !value.endsWith('+clerk_test@example.com')) {
    throw Object.assign(new Error(`${name} must be a reserved Clerk test email.`), { runnerCode: 3 })
  }
  return value
}

function parseDatabaseUrl(value) {
  return new URL(value.replace(/^postgresql\+[^:]+:/, 'postgresql:'))
}

export function validateDatabaseTargets({ runtimeUrl, migrationUrl, host, port, database }) {
  let runtime
  let migration
  try {
    runtime = parseDatabaseUrl(runtimeUrl)
    migration = parseDatabaseUrl(migrationUrl)
  } catch {
    throw Object.assign(new Error('Database URLs must be valid PostgreSQL URLs.'), { runnerCode: 3 })
  }
  const expected = { hostname: host, port: String(port), pathname: `/${database}` }
  for (const [name, url] of [['runtime', runtime], ['migration', migration]]) {
    if (url.hostname !== expected.hostname || url.port !== expected.port || url.pathname !== expected.pathname) {
      throw Object.assign(new Error(`The ${name} database URL is outside the owned test database.`), { runnerCode: 3 })
    }
  }
  if (runtime.hostname !== migration.hostname || runtime.port !== migration.port || runtime.pathname !== migration.pathname) {
    throw Object.assign(new Error('Runtime and migration database URLs must target the same database.'), { runnerCode: 3 })
  }
}

function validateE2eEnvironment() {
  const publishableKey = process.env.VITE_CLERK_PUBLISHABLE_KEY || ''
  const secretKey = process.env.CLERK_SECRET_KEY || ''
  if (!publishableKey.startsWith('pk_test_')) {
    throw Object.assign(new Error('VITE_CLERK_PUBLISHABLE_KEY must be a pk_test_ key.'), { runnerCode: 3 })
  }
  if (!secretKey.startsWith('sk_test_')) {
    throw Object.assign(new Error('CLERK_SECRET_KEY must be an sk_test_ key.'), { runnerCode: 3 })
  }
  const adminEmail = ensureTestEmail(process.env.E2E_CLERK_ADMIN_EMAIL, 'E2E_CLERK_ADMIN_EMAIL')
  const teacherEmail = ensureTestEmail(process.env.E2E_CLERK_TEACHER_EMAIL, 'E2E_CLERK_TEACHER_EMAIL')
  const runKey = `${Date.now()}-${process.pid}`
  return {
    publishableKey,
    secretKey,
    adminEmail,
    teacherEmail,
    inviteCreateEmail: ensureTestEmail(
      process.env.E2E_CLERK_INVITE_CREATE_EMAIL || `e2e-create-${runKey}+clerk_test@example.com`,
      'E2E_CLERK_INVITE_CREATE_EMAIL',
    ),
    inviteConvertEmail: ensureTestEmail(
      process.env.E2E_CLERK_INVITE_CONVERT_EMAIL || `e2e-convert-${runKey}+clerk_test@example.com`,
      'E2E_CLERK_INVITE_CONVERT_EMAIL',
    ),
  }
}

async function ensurePortAvailable(port) {
  await new Promise((resolvePromise, rejectPromise) => {
    const server = net.createServer()
    server.once('error', () => rejectPromise(new Error(`E2E port ${port} is already in use.`)))
    server.listen(port, '127.0.0.1', () => server.close(resolvePromise))
  })
}

async function startTestStack(context, { full = false } = {}) {
  const e2eEnvironment = full ? validateE2eEnvironment() : null
  if (full) await ensurePortAvailable(E2E_PORT)
  const token = `${Date.now()}-${process.pid}-${randomBytes(4).toString('hex')}`
  const project = `cronos-test-${token}`
  const postgresPassword = randomBytes(24).toString('hex')
  const migratorPassword = randomBytes(24).toString('hex')
  const appPassword = randomBytes(24).toString('hex')
  const composeEnv = {
    ...process.env,
    COMPOSE_PROJECT_NAME: project,
    POSTGRES_DB: 'cronos_test_db',
    POSTGRES_PASSWORD: postgresPassword,
    CRONOS_MIGRATOR_PASSWORD: migratorPassword,
    CRONOS_APP_PASSWORD: appPassword,
    ...(full ? {
      CLERK_SECRET_KEY: e2eEnvironment.secretKey,
      E2E_CLERK_ADMIN_EMAIL: e2eEnvironment.adminEmail,
      E2E_CLERK_TEACHER_EMAIL: e2eEnvironment.teacherEmail,
      E2E_CLERK_INVITE_CREATE_EMAIL: e2eEnvironment.inviteCreateEmail,
      E2E_CLERK_INVITE_CONVERT_EMAIL: e2eEnvironment.inviteConvertEmail,
      E2E_CLERK_ORG_ID: '',
      E2E_CLERK_CREATE_ORGANIZATION: 'true',
    } : {}),
  }
  const compose = (rest) => composeSpec({ project, rest })
  const stack = {
    project,
    composeEnv,
    migratorPassword,
    started: true,
    full,
    ownedResourceIds: new Set([project]),
    compose,
  }
  context.stack = stack
  if (full) {
    await runChecked(compose(['build', 'backend', 'frontend']), {
      env: composeEnv, label: 'build test application stack', environmentFailure: true,
    })
  }
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
  const runtimeDatabaseUrl = `postgresql+asyncpg://cronos_app:${appPassword}@127.0.0.1:${dbPort}/cronos_test_db`
  const migrationDatabaseUrl = `postgresql+psycopg2://cronos_migrator:${migratorPassword}@127.0.0.1:${dbPort}/cronos_test_db`
  validateDatabaseTargets({
    runtimeUrl: runtimeDatabaseUrl,
    migrationUrl: migrationDatabaseUrl,
    host: '127.0.0.1',
    port: dbPort,
    database: 'cronos_test_db',
  })

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
  for (let worker = 0; worker < INTEGRATION_WORKERS; worker += 1) {
    const database = `cronos_test_gw${worker}`
    await runChecked(psql('postgres', `CREATE DATABASE ${database} OWNER cronos_migrator;`), {
      env: composeEnv, label: `create ${database}`, environmentFailure: true,
    })
    await runChecked(psql('postgres', `GRANT CONNECT ON DATABASE ${database} TO cronos_app;`), {
      env: composeEnv, label: `grant ${database} access`, environmentFailure: true,
    })
  }

  if (full) {
    await runChecked(compose(['--profile', 'maintenance', 'run', '--rm', 'db-maintenance']), {
      env: composeEnv, label: 'apply test application migrations', environmentFailure: true,
    })
    await runChecked(compose(['up', '-d', '--wait', 'backend', 'worker', 'beat', 'frontend']), {
      env: composeEnv, label: 'start test application stack', environmentFailure: true,
    })
  }

  Object.assign(stack, {
    dbPort,
    redisPort,
    frontendPort: full ? E2E_PORT : null,
    env: baseTestEnvironment({
      DATABASE_URL: runtimeDatabaseUrl,
      MIGRATION_DATABASE_URL: migrationDatabaseUrl,
      TEST_DATABASE_URL: runtimeDatabaseUrl,
      REDIS_URL: `redis://127.0.0.1:${redisPort}/0`,
      CELERY_BROKER_URL: `redis://127.0.0.1:${redisPort}/0`,
      ...(full ? {
        BASE_URL: resolveE2eBaseUrl(),
        FRONTEND_URL: resolveE2eBaseUrl(),
        CLERK_AUTHORIZED_PARTIES: resolveE2eBaseUrl(),
        CLERK_SECRET_KEY: e2eEnvironment.secretKey,
        VITE_CLERK_PUBLISHABLE_KEY: e2eEnvironment.publishableKey,
        E2E_CLERK_ADMIN_EMAIL: e2eEnvironment.adminEmail,
        E2E_CLERK_TEACHER_EMAIL: e2eEnvironment.teacherEmail,
        E2E_CLERK_INVITE_CREATE_EMAIL: e2eEnvironment.inviteCreateEmail,
        E2E_CLERK_INVITE_CONVERT_EMAIL: e2eEnvironment.inviteConvertEmail,
        E2E_CLERK_AUTO_PROVISION: process.env.E2E_CLERK_AUTO_PROVISION || 'true',
        PLAYWRIGHT_SKIP_WEB_SERVER: '1',
        PLAYWRIGHT_WORKERS: String(E2E_WORKERS),
      } : {}),
    }),
  })
  if (full) stack.e2eEnvironment = e2eEnvironment
  await writeFile(join(context.artifactDir, 'stack.json'), `${JSON.stringify({
    runId: context.runId,
    project,
    dbPort,
    redisPort,
    databases: [
      'cronos_test_db',
      ...Array.from({ length: INTEGRATION_WORKERS }, (_, worker) => `cronos_test_gw${worker}`),
    ],
  }, null, 2)}\n`)
  context.stack = stack
  return stack
}

async function prepareE2eClerkState(context) {
  const stack = context.stack
  if (!stack?.full) return
  const output = await runCapture(stack.compose([
    'exec', '-T',
    '-e', `DATABASE_URL=postgresql+asyncpg://cronos_migrator:${stack.migratorPassword}@db:5432/cronos_test_db`,
    'backend', 'python', 'scripts/prepare_e2e_clerk_state.py',
  ]), {
    env: stack.composeEnv,
    label: 'prepare isolated E2E Clerk state',
  })
  let result
  try {
    result = JSON.parse(output)
  } catch {
    throw Object.assign(new Error('E2E Clerk preparation returned invalid JSON.'), { runnerCode: 3 })
  }
  if (!result.clerk_org_id) {
    throw Object.assign(new Error('E2E Clerk preparation returned no organization ID.'), { runnerCode: 3 })
  }
  stack.e2ePrepared = true
  stack.env = {
    ...stack.env,
    E2E_CLERK_ORG_ID: result.clerk_org_id,
  }
  context.e2eOrganizationId = result.clerk_org_id
}

async function cleanupE2eClerkState(context) {
  const stack = context.stack
  if (!stack?.full || !stack.e2ePrepared) return 0
  const result = await spawnProcess(
    stack.compose([
      'exec', '-T',
      '-e', `DATABASE_URL=postgresql+asyncpg://cronos_migrator:${stack.migratorPassword}@db:5432/cronos_test_db`,
      '-e', 'E2E_CLERK_DELETE_ORG=true',
      'backend', 'python', 'scripts/cleanup_e2e_clerk_invitations.py',
    ]),
    { env: stack.composeEnv, label: 'cleanup owned E2E Clerk invitations' },
  )
  return result.code
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
  const preparationStartedAt = monotonicMs()
  const stack = await startTestStack(context)
  addPhaseTime(context, 'preparation_ms', Math.round(monotonicMs() - preparationStartedAt))
  try {
    const prefix = coverage
      ? ['-m', 'pytest', '--cov=app', '--cov-branch', '--cov-report=', '--cov-fail-under=0', '--cov-append']
      : ['-m', 'pytest']
    const integrationReport = join(context.artifactDir, 'backend-integration.xml')
    const integrationArgs = [
      ...prefix,
      '-c',
      join(BACKEND, 'pyproject.toml'),
      join(BACKEND, 'tests', 'integration'),
      '-n',
      String(INTEGRATION_WORKERS),
      '--dist=loadscope',
      `--junitxml=${integrationReport}`,
      ...forwarded,
    ]
    await runRecorded(backendPythonSpec(integrationArgs, stack.env, context, stack), {
      cwd: BACKEND, env: stack.env, label: 'backend integration tests',
    }, context, {
      name: 'backend-integration',
      kind: 'pytest',
      reportPath: integrationReport,
      workers: INTEGRATION_WORKERS,
    })
    const contractPrefix = coverage
      ? ['-m', 'pytest', '--cov=app', '--cov-branch', '--cov-report=', '--cov-fail-under=0', '--cov-append']
      : ['-m', 'pytest']
    const contractReport = join(context.artifactDir, 'backend-contracts.xml')
    await runRecorded(backendPythonSpec([
      ...contractPrefix,
      '-c',
      join(BACKEND, 'pyproject.toml'),
      join(BACKEND, 'tests', 'contracts'),
      `--junitxml=${contractReport}`,
    ], stack.env, context, stack), {
      cwd: BACKEND, env: stack.env, label: 'backend infrastructure contracts',
    }, context, {
      name: 'backend-contracts',
      kind: 'pytest',
      reportPath: contractReport,
      workers: 1,
    })
  } finally {
    context.stack = stack
  }
}

async function runE2e(project, context, extraEnv = {}) {
  const externalStack = process.env.E2E_EXTERNAL_STACK === '1'
  const preparationStartedAt = monotonicMs()
  if (externalStack) {
    validateE2eEnvironment()
    context.e2eWorkers = E2E_WORKERS
  } else {
    await startTestStack(context, { full: true })
    await prepareE2eClerkState(context)
    context.e2eWorkers = E2E_WORKERS
  }
  addPhaseTime(context, 'preparation_ms', Math.round(monotonicMs() - preparationStartedAt))
  const args = ['run', 'test:e2e', '--']
  if (project) args.push('--project', project)
  const capacityEnv = project === 'capacity'
    ? {
        CAPACITY_ENABLED: '1',
        CAPACITY_PROFILE: 'full',
        CAPACITY_DURATION_SECONDS: '600',
        CAPACITY_REPORT_PATH: join(context.artifactDir, 'capacity.json'),
      }
    : {}
  const e2eEnv = externalStack
    ? {
        ...process.env,
        E2E_COMPOSE_FILE: join(ROOT, 'docker-compose.ci.yml'),
        BASE_URL: resolveE2eBaseUrl({ externalStack: true, baseUrl: process.env.BASE_URL }),
        PLAYWRIGHT_SKIP_WEB_SERVER: '1',
        PLAYWRIGHT_WORKERS: String(E2E_WORKERS),
        ...capacityEnv,
        ...extraEnv,
      }
    : {
        ...context.stack.env,
        E2E_COMPOSE_FILE: COMPOSE_FILE,
        ...capacityEnv,
        ...extraEnv,
      }
  await runFrontendTests(
    args,
    `Playwright ${project || 'all'}`,
    e2eEnv,
    context,
    `e2e-${project || 'all'}`,
  )
  context.e2e = project || 'all'
}

async function runAllBackend(context) {
  await runChecked(backendPythonSpec(['-m', 'ruff', 'format', '--check', BACKEND], baseTestEnvironment(), context), {
    cwd: ROOT, env: baseTestEnvironment(), label: 'Ruff format check',
  })
  await runChecked(backendPythonSpec(['-m', 'ruff', 'check', BACKEND], baseTestEnvironment(), context), {
    cwd: ROOT, env: baseTestEnvironment(), label: 'Ruff lint',
  })
  const unitReport = join(context.artifactDir, 'backend-unit.xml')
  await runRecorded(backendPythonSpec([
    '-m', 'pytest', '--cov=app', '--cov-branch', '--cov-report=', '--cov-fail-under=0',
    '-c', join(BACKEND, 'pyproject.toml'), join(BACKEND, 'tests', 'unit'),
    '--disable-socket', '--allow-hosts=127.0.0.1,localhost', `--junitxml=${unitReport}`,
  ], baseTestEnvironment(), context), {
    cwd: BACKEND, env: baseTestEnvironment(), label: 'backend unit tests with coverage',
  }, context, {
    name: 'backend-unit',
    kind: 'pytest',
    reportPath: unitReport,
    workers: 1,
  })
  await runIntegration([], context, { coverage: true })
  const coverageStartedAt = monotonicMs()
  await runChecked(backendPythonSpec(['-m', 'coverage', 'report', '--fail-under=70'], baseTestEnvironment(), context), {
    cwd: BACKEND, env: baseTestEnvironment(), label: 'backend coverage gate',
  })
  await runChecked(backendPythonSpec([
    '-m', 'coverage', 'report',
    '--include=app/scheduler/domain/constraint_policy.py',
    '--fail-under=100',
  ], baseTestEnvironment(), context), {
    cwd: BACKEND, env: baseTestEnvironment(), label: 'scheduler coverage gate',
  })
  addPhaseTime(context, 'coverage_ms', Math.round(monotonicMs() - coverageStartedAt))
}

async function runAllFrontend(context) {
  await runFrontendTests(['run', 'lint'], 'ESLint', {}, context, 'eslint')
  await runFrontendTests(['run', 'lint:dead-code'], 'Knip', {}, context, 'knip')
  await runFrontendTests(['run', 'lint:dead-code:production'], 'Knip production', {}, context, 'knip-production')
  await runFrontendTests(['run', 'test:marketing-build'], 'Node script tests', {}, context, 'marketing-build')
  await runFrontendTests(['run', 'test:marketing-assets'], 'Asset audit', {}, context, 'marketing-assets')
  await runFrontendTests(['run', 'test:coverage'], 'Vitest coverage', {}, context, 'frontend-coverage', 'coverage_ms')
  await runFrontendTests(['run', 'build'], 'Frontend build', {}, context, 'frontend-build')
  await runFrontendTests(['run', 'audit:production'], 'Production dependency audit', {}, context, 'frontend-audit')
}

async function runAll(scope, context) {
  if (scope === 'backend' || scope === 'all') await runAllBackend(context)
  if (scope === 'frontend' || scope === 'all') await runAllFrontend(context)
}

function aggregateCounts(suites) {
  const fields = ['collected', 'passed', 'failed', 'skipped', 'errors']
  return Object.fromEntries(fields.map((field) => {
    const values = suites.map((suite) => suite[field])
    return [field, values.every((value) => Number.isInteger(value))
      ? values.reduce((sum, value) => sum + value, 0)
      : null]
  }))
}

async function environmentSnapshot() {
  const version = async (spec) => {
    try {
      return (await runCapture(spec)).split(/\r?\n/, 1)[0].trim()
    } catch {
      return null
    }
  }
  return {
    operating_system: `${os.platform()} ${os.release()}`,
    architecture: os.arch(),
    cpu: os.cpus()[0]?.model || null,
    logical_cpus: os.cpus().length,
    memory_bytes: os.totalmem(),
    node: process.version,
    npm: await version(npmSpec(['--version'])),
    python: await version(childSpec(executable('python'), ['--version'])),
    docker: await version(childSpec(executable('docker'), ['--version'])),
    compose: await version(childSpec(executable('docker'), ['compose', 'version'])),
  }
}

async function gitSnapshot() {
  let clean = null
  let tree = null
  try {
    const status = await runCapture(childSpec(executable('git'), [
      'status', '--porcelain=v1', '--untracked-files=all',
    ]))
    clean = status.length === 0
    const head = await runCapture(childSpec(executable('git'), ['rev-parse', 'HEAD']))
    const diff = await runCapture(childSpec(executable('git'), ['diff', '--binary']))
    const staged = await runCapture(childSpec(executable('git'), ['diff', '--cached', '--binary']))
    const untracked = status
      .split(/\r?\n/)
      .filter((line) => line.startsWith('?? '))
      .map((line) => line.slice(3).trim())
    const digests = []
    for (const relative of untracked) {
      const content = await readFile(join(ROOT, relative)).catch(() => null)
      if (content) digests.push(createHash('sha256').update(content).digest('hex'))
    }
    tree = createHash('sha256')
      .update([head, status, diff, staged, ...digests].join('\n'))
      .digest('hex')
  } catch {
    // The revision remains useful when Git status is unavailable.
  }
  return { clean, tree }
}

async function writeRunReport(context, parsed, exitCode, cleanupCode) {
  const totalMs = Math.round(monotonicMs() - context.startedAt)
  const report = {
    revision: context.revision,
    git: context.git,
    environment: context.environment,
    command: parsed.command,
    scope: parsed.scope,
    profile: parsed.profile,
    project: parsed.project ?? null,
    workers: {
      integration: INTEGRATION_WORKERS,
      e2e: context.e2eWorkers ?? null,
    },
    timings: {
      preparation_ms: context.timings.preparation_ms,
      tests_ms: context.timings.tests_ms,
      coverage_ms: context.timings.coverage_ms,
      cleanup_ms: context.timings.cleanup_ms,
      total_ms: totalMs,
    },
    totals: aggregateCounts(context.suites),
    suites: context.suites,
    exit_code: exitCode,
    cleanup_exit_code: cleanupCode,
  }
  await writeFile(join(context.artifactDir, 'run.json'), `${JSON.stringify(report, null, 2)}\n`)
  return report
}

function benchmarkCommand(profile, scope) {
  if (profile === 'fast') return ['fast', '--scope', scope]
  if (profile === 'all') return ['all', '--scope', 'all']
  return [profile]
}

function median(values) {
  const sorted = [...values].sort((left, right) => left - right)
  return sorted[Math.floor(sorted.length / 2)]
}

async function runBenchmark(profile, scope, context) {
  const benchmarkDir = join(context.artifactDir, `benchmark-${profile}-${scope}`)
  await mkdir(benchmarkDir, { recursive: true })
  const samples = []
  let invalid = false

  for (let sample = 0; sample <= 5; sample += 1) {
    const warmup = sample === 0
    const sampleName = warmup ? 'warmup' : `sample-${sample}`
    const sampleDir = join(benchmarkDir, sampleName)
    await mkdir(sampleDir, { recursive: true })
    if (warmup) {
      await rm(join(FRONTEND, 'node_modules', '.vite'), { recursive: true, force: true })
      await rm(join(FRONTEND, 'node_modules', '.vitest'), { recursive: true, force: true })
    }
    const startedAt = monotonicMs()
    const child = await spawnProcess(
      childSpec(process.execPath, [fileURLToPath(import.meta.url), ...benchmarkCommand(profile, scope)]),
      {
        cwd: ROOT,
        env: {
          ...process.env,
          TEST_ARTIFACT_DIR: sampleDir,
          TEST_BENCHMARK_SAMPLE: sampleName,
          TEST_BENCHMARK_PARENT: context.runId,
        },
        label: `benchmark ${profile}/${scope} ${sampleName}`,
      },
    )
    const reportPath = join(sampleDir, 'run.json')
    const report = await access(reportPath).then(() => readFile(reportPath, 'utf8'))
      .then((value) => JSON.parse(value))
      .catch(() => null)
    const durationMs = report?.timings?.total_ms ?? Math.round(monotonicMs() - startedAt)
    const sampleReport = {
      sample: sampleName,
      warmup,
      cache_state: warmup ? 'cold' : 'warm',
      duration_ms: durationMs,
      exit_code: child.code,
      report: report ? `${sampleName}/run.json` : null,
      totals: report?.totals ?? null,
      timings: report?.timings ?? null,
    }
    samples.push(sampleReport)
    if (child.code !== 0) {
      invalid = true
      break
    }
  }

  const validSamples = samples.filter((sample) => !sample.warmup && sample.exit_code === 0)
  const summary = {
    revision: context.revision,
    profile,
    scope,
    warmup: samples.find((sample) => sample.warmup) ?? null,
    samples: validSamples,
    invalid,
    median_ms: !invalid && validSamples.length === 5 ? median(validSamples.map((sample) => sample.duration_ms)) : null,
    minimum_ms: !invalid && validSamples.length === 5 ? Math.min(...validSamples.map((sample) => sample.duration_ms)) : null,
    maximum_ms: !invalid && validSamples.length === 5 ? Math.max(...validSamples.map((sample) => sample.duration_ms)) : null,
  }
  await writeFile(join(context.artifactDir, `benchmark-${profile}-${scope}.json`), `${JSON.stringify(summary, null, 2)}\n`)
  if (invalid || validSamples.length !== 5) {
    throw Object.assign(new Error(`Benchmark ${profile}/${scope} is invalid.`), { runnerCode: 1 })
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
  const artifactDir = process.env.TEST_ARTIFACT_DIR
    ? resolve(process.env.TEST_ARTIFACT_DIR)
    : join(ARTIFACTS, runId)
  await mkdir(artifactDir, { recursive: true })
  const context = {
    runId,
    artifactDir,
    revision: await currentRevision(),
    git: await gitSnapshot(),
    environment: await environmentSnapshot(),
    prepared: {},
    suites: [],
    startedAt: monotonicMs(),
    timings: {
      preparation_ms: null,
      tests_ms: null,
      coverage_ms: null,
      cleanup_ms: null,
    },
  }
  let primaryCode = 0
  try {
    if (parsed.command === 'setup') await runSetup(parsed.scope, context)
    else if (parsed.command === 'doctor') await runDoctor(parsed.profile, context)
    else if (parsed.command === 'fast') await runFast(parsed.scope, parsed.forwarded, context)
    else if (parsed.command === 'integration') await runIntegration(parsed.forwarded, context)
    else if (parsed.command === 'e2e') await runE2e(parsed.project, context)
    else if (parsed.command === 'capacity') await runE2e('capacity', context)
    else if (parsed.command === 'capacity-smoke') {
      await runE2e('capacity', context, {
        CAPACITY_ENABLED: '1',
        CAPACITY_PROFILE: 'smoke',
        CAPACITY_DURATION_SECONDS: '30',
        CAPACITY_REPORT_PATH: join(context.artifactDir, 'capacity-smoke.json'),
      })
    }
    else if (parsed.command === 'all') await runAll(parsed.scope, context)
    else if (parsed.command === 'benchmark') await runBenchmark(parsed.profile, parsed.scope, context)
    else if (parsed.command === 'campaign') await runCampaign(parsed, context)
  } catch (error) {
    primaryCode = error.runnerCode || 1
    console.error(`[test] ${error.message}`)
    if (error.result?.stderr) console.error(error.result.stderr)
  }
  let cleanupCode = 0
  const cleanupStartedAt = monotonicMs()
  try {
    const clerkCleanupCode = await cleanupE2eClerkState(context)
    cleanupCode = await stopTestStack(context)
    cleanupCode = cleanupCode || clerkCleanupCode
  } catch (error) {
    cleanupCode = 3
    console.error(`[test] cleanup failed: ${error.message}`)
  }
  context.timings.cleanup_ms = Math.round(monotonicMs() - cleanupStartedAt)
  const exitCode = preservePrimaryFailure(primaryCode, cleanupCode ? 3 : 0)
  await writeRunReport(context, parsed, exitCode, cleanupCode)
  return exitCode
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().then((code) => { process.exitCode = code }).catch((error) => {
    console.error(error)
    process.exitCode = 3
  })
}
