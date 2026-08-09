import { copyFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

copyFileSync(
  fileURLToPath(new URL('../website/_headers', import.meta.url)),
  fileURLToPath(new URL('../dist-website/_headers', import.meta.url)),
)
