import { spawnSync } from 'node:child_process'

const audit = spawnSync(
  process.execPath,
  [process.env.npm_execpath, 'audit', '--omit=dev', '--audit-level=high', '--json'],
  { encoding: 'utf8' },
)
const report = JSON.parse(audit.stdout)
const vulnerabilities = report.vulnerabilities ?? {}
const allowed = new Set(['react-router', 'react-router-dom'])
const rscCsrfAdvisory = 'https://github.com/advisories/GHSA-qwww-vcr4-c8h2'

const unexpected = Object.entries(vulnerabilities).filter(([name, vulnerability]) => {
  if (!allowed.has(name) || vulnerability.severity !== 'high') return true
  return name === 'react-router' && !vulnerability.via.some(
    (entry) => typeof entry === 'object' && entry.url === rscCsrfAdvisory,
  )
})

if (unexpected.length) {
  process.stderr.write(audit.stdout)
  process.exit(1)
}

// React Router has no published version outside this advisory's affected range.
// Remove this exception when one is released; all other production highs still fail.
console.log('Allowed production advisory: GHSA-qwww-vcr4-c8h2 (React Router RSC mode).')
