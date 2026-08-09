import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const distUrl = new URL('../dist-website/', import.meta.url)
const dist = fileURLToPath(distUrl)
const required = ['index.html', '404.html', 'robots.txt', 'sitemap.xml']
const markers = ['ClerkProvider', 'VITE_CLERK', 'SignInPage', '/dashboard', '/create-org', '/onboarding']

for (const file of required) {
  if (!existsSync(new URL(file, distUrl))) throw new Error(`Missing website asset: ${file}`)
}

const manifest = JSON.parse(readFileSync(new URL('.vite/manifest.json', distUrl), 'utf8'))
if (!manifest['index.html']) throw new Error('Vite manifest does not identify the website entry.')
const headers = readFileSync(new URL('_headers', distUrl), 'utf8')
for (const marker of ['Clerk', 'api.cronos.pt', 'Strict-Transport-Security']) {
  if (headers.includes(marker)) throw new Error(`Website headers contain forbidden marker: ${marker}`)
}

function walk(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name)
    return entry.isDirectory() ? walk(path) : [path]
  })
}

for (const file of walk(dist)) {
  if (file.endsWith('.map')) throw new Error(`Source map found: ${file}`)
  if (file.endsWith('.html') || file.endsWith('.js')) {
    const content = readFileSync(file, 'utf8')
    const marker = markers.find((value) => content.includes(value))
    if (marker) throw new Error(`Application marker found: ${marker}`)
  }
}
