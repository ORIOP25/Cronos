import { spawnSync } from 'node:child_process'

const audit = spawnSync(
  process.execPath,
  [process.env.npm_execpath, 'audit', '--omit=dev', '--audit-level=high', '--json'],
  { encoding: 'utf8' },
)
const report = JSON.parse(audit.stdout)
const vulnerabilities = report.vulnerabilities ?? {}

if (Object.keys(vulnerabilities).length) {
  process.stderr.write(audit.stdout)
  process.exit(1)
}

console.log('Production dependency audit passed with no reported vulnerabilities.')
