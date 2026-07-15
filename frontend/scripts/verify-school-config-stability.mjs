import { spawnSync } from 'node:child_process'

for (let run = 1; run <= 10; run += 1) {
  const result = spawnSync(
    process.execPath,
    ['./node_modules/vitest/vitest.mjs', 'run', 'src/test/SchoolConfigSchedulerSettings.test.jsx', '--maxWorkers=1'],
    { stdio: 'inherit' },
  )
  if (result.status !== 0) process.exit(result.status || 1)
}
