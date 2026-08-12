import { createHash } from 'node:crypto'
import { readdir, readFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDirectory = dirname(fileURLToPath(import.meta.url))
const productDirectory = join(scriptDirectory, '..', 'public', 'marketing', 'product')
const allowedFiles = new Set(['hero-schedule.png', 'hero-schedule.webp'])
const files = (await readdir(productDirectory)).filter((file) => file.endsWith('.png') || file.endsWith('.webp'))

const hashes = new Map()
for (const file of files) {
  if (!allowedFiles.has(file)) throw new Error(`Unexpected marketing product asset: ${file}`)
  const hash = createHash('sha256').update(await readFile(join(productDirectory, file))).digest('hex')
  const previousFile = hashes.get(hash)
  if (previousFile) throw new Error(`Duplicate marketing product asset content: ${previousFile} and ${file}`)
  hashes.set(hash, file)
}

if (files.length !== allowedFiles.size) throw new Error('Expected only the single approved hero asset pair.')
console.log(`Marketing asset audit passed: ${files.join(', ')}`)
