import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

const backendLegal = await readFile(resolve(process.cwd(), '..', 'backend', 'app', 'legal.py'), 'utf8')
const publicLegal = await readFile(resolve(process.cwd(), 'src', 'features', 'legal', 'content.jsx'), 'utf8')
const termsVersion = backendLegal.match(/CURRENT_TERMS_VERSION\s*=\s*["']([^"']+)["']/)?.[1]
const dpaVersion = backendLegal.match(/CURRENT_DPA_VERSION\s*=\s*["']([^"']+)["']/)?.[1]
const publicVersion = publicLegal.match(/LEGAL_VERSION\s*=\s*["']([^"']+)["']/)?.[1]

if (!termsVersion || !dpaVersion || !publicVersion || termsVersion !== dpaVersion || termsVersion !== publicVersion) {
  throw new Error(`Legal version mismatch: backend terms=${termsVersion}, dpa=${dpaVersion}, public=${publicVersion}`)
}

console.log(`Legal version contract passed: ${termsVersion}`)
