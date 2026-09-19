import { execFileSync } from 'node:child_process'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

export const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
export const BASELINE_PATH = join(ROOT, 'documentation', '08_security_quality', 'loc-baseline.json')

const CATEGORIES = ['backendProduction', 'frontendProduction', 'backendTests', 'frontendTests', 'e2eTests']
const SOURCE_EXTENSIONS = new Set(['.css', '.js', '.jsx', '.py', '.ts', '.tsx'])

function normalize(filePath) {
  return filePath.replaceAll('\\', '/').replace(/^\.\//, '')
}

function isExcluded(filePath) {
  const path = normalize(filePath).toLowerCase()
  const segments = path.split('/')
  const excludedDirectory = new Set(['.git', '.venv', 'build', 'coverage', 'dist', 'node_modules', 'playwright-report', 'test-results'])
  return segments.some((segment) => excludedDirectory.has(segment))
    || /(^|\/)(generated|migrations|alembic\/versions)(\/|$)/.test(path)
    || /(^|\/)(documentation|\.test-artifacts)(\/|$)/.test(path)
    || /(^|\/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|requirements[^/]*\.txt)$/.test(path)
}

export function classifyPath(filePath) {
  const path = normalize(filePath)
  const lower = path.toLowerCase()
  if (isExcluded(path)) return null
  if (lower.startsWith('backend/tests/') && lower.endsWith('.py')) return 'backendTests'
  if (lower.startsWith('frontend/e2e/') && SOURCE_EXTENSIONS.has(extension(path))) return 'e2eTests'
  if (lower.startsWith('frontend/src/test/') && SOURCE_EXTENSIONS.has(extension(path))) return 'frontendTests'
  if (lower.startsWith('backend/app/') && extension(path) === '.py') return 'backendProduction'
  if (lower.startsWith('frontend/src/') && SOURCE_EXTENSIONS.has(extension(path))) return 'frontendProduction'
  return null
}

function extension(filePath) {
  const dot = filePath.lastIndexOf('.')
  return dot === -1 ? '' : filePath.slice(dot).toLowerCase()
}

export function countNonBlankLines(contents) {
  return contents.split(/\r?\n/).reduce((count, line) => count + (line.trim() ? 1 : 0), 0)
}

export function collectFiles(gitOutput) {
  return gitOutput.split(/\r?\n/).map((filePath) => filePath.trim()).filter(Boolean)
}

export function measureFiles(files, read = (filePath) => readFileSync(filePath, 'utf8'), exists = existsSync) {
  const counts = Object.fromEntries(CATEGORIES.map((category) => [category, 0]))
  const measuredFiles = []
  for (const filePath of files) {
    const category = classifyPath(filePath)
    if (!category) continue
    const absolutePath = join(ROOT, filePath)
    if (!exists(absolutePath)) continue
    const contents = read(absolutePath)
    if (contents.includes('\0')) continue
    const lines = countNonBlankLines(contents)
    counts[category] += lines
    measuredFiles.push({ path: normalize(filePath), category, lines })
  }
  return { counts, files: measuredFiles }
}

function currentRevision() {
  const safePath = process.platform === 'win32'
    ? 'C:\\Windows\\System32;C:\\Program Files\\Git\\cmd'
    : '/usr/local/bin:/usr/bin:/bin'
  return execFileSync('git', ['rev-parse', 'HEAD'], {
    cwd: ROOT,
    encoding: 'utf8',
    env: { ...process.env, PATH: safePath },
  }).trim()
}

export function report({ baseline = null, revision = currentRevision() } = {}) {
  const gitOutput = execFileSync('git', ['ls-files', '--cached', '--others', '--exclude-standard'], {
    cwd: ROOT,
    encoding: 'utf8',
  })
  const measured = measureFiles(collectFiles(gitOutput))
  const deltas = Object.fromEntries(CATEGORIES.map((category) => [
    category,
    measured.counts[category] - (baseline?.counts?.[category] ?? measured.counts[category]),
  ]))
  return { revision, counts: measured.counts, deltas, files: measured.files }
}

function formatDelta(delta) {
  return delta > 0 ? `+${delta}` : String(delta)
}

export function printReport(result, hasBaseline) {
  console.log('LOC report (nonblank lines)')
  for (const category of CATEGORIES) {
    const delta = hasBaseline ? ` (${formatDelta(result.deltas[category])})` : ''
    console.log(`${category}: ${result.counts[category]}${delta}`)
  }
  console.log(`totalProduction: ${result.counts.backendProduction + result.counts.frontendProduction}`)
  console.log(`totalTests: ${result.counts.backendTests + result.counts.frontendTests + result.counts.e2eTests}`)
  console.log(`measuredFiles: ${result.files.length}`)
  console.log(`revision: ${result.revision}`)
}

function main() {
  const writeBaseline = process.argv.includes('--write-baseline')
  const baseline = existsSync(BASELINE_PATH) ? JSON.parse(readFileSync(BASELINE_PATH, 'utf8')) : null
  const result = report({ baseline })
  printReport(result, Boolean(baseline))
  if (writeBaseline) {
    writeFileSync(BASELINE_PATH, `${JSON.stringify({ revision: result.revision, counts: result.counts }, null, 2)}\n`)
    console.log(`baseline: ${relative(ROOT, BASELINE_PATH)}`)
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main()
