import test from 'node:test'
import assert from 'node:assert/strict'
import worker, { acceptsMarkdown, isKnownApplicationRoute } from '../public/_worker.js'

const assets = new Map([
  ['/index.html', { body: '<html><div id="root">legacy-index-path</div></html>', contentType: 'text/html; charset=utf-8' }],
  ['/', { body: '<html><div class="cronos-hero">home</div></html>', contentType: 'text/html; charset=utf-8' }],
  ['/app-shell', { body: '<html><div id="root"></div></html>', contentType: 'text/html; charset=utf-8' }],
  ['/llms.txt', { body: '# Cronos', contentType: 'text/plain; charset=utf-8' }],
  ['/404', { body: '<h1>404</h1><a href="/">Voltar ao início</a>', contentType: 'text/html; charset=utf-8' }],
  ['/404.md', { body: '# 404 — Página não encontrada', contentType: 'text/plain; charset=utf-8' }],
  ['/sobre', { body: '<h1>Sobre</h1>', contentType: 'text/html; charset=utf-8' }],
  ['/about', { body: '<h1>Sobre</h1>', contentType: 'text/html; charset=utf-8' }],
  ['/assets/main-abc12345.js', { body: 'console.log(1)', contentType: 'text/javascript' }],
  ['/logo.png', { body: 'png', contentType: 'image/png' }],
  ['/favicon.png', { body: 'png', contentType: 'image/png' }],
  ['/marketing/hero.webp', { body: 'webp', contentType: 'image/webp' }],
])

function createEnvironment() {
  const calls = []
  return {
    calls,
    env: {
      ASSETS: {
        fetch(request) {
          const url = new URL(request.url)
          calls.push({ method: request.method, pathname: url.pathname })
          if (url.pathname === '/404.html') {
            return Promise.resolve(new Response(null, { status: 308, headers: { Location: '/404' } }))
          }
          const asset = assets.get(url.pathname + url.search)
          if (!asset) return Promise.resolve(new Response('missing', { status: 404 }))
          return Promise.resolve(new Response(asset.body, { headers: { 'Content-Type': asset.contentType, ...(url.pathname === '/' ? { Vary: 'Accept-Encoding' } : {}) } }))
        },
      },
    },
  }
}

async function request(pathname, init = {}) {
  const { env, calls } = createEnvironment()
  const response = await worker.fetch(new Request(`https://cronos.pt${pathname}`, init), env)
  return { response, calls }
}

test('parses explicit Markdown acceptance and rejects q=0', () => {
  assert.equal(acceptsMarkdown('text/markdown, text/html;q=0.9'), true)
  assert.equal(acceptsMarkdown('text/markdown;q=0, text/html;q=1'), false)
  assert.equal(acceptsMarkdown('text/html, */*;q=0.8'), false)
})

test('classifies only declared application routes', () => {
  assert.equal(isKnownApplicationRoute('/dashboard'), true)
  assert.equal(isKnownApplicationRoute('/courses/course/classes/class/subjects'), true)
  assert.equal(isKnownApplicationRoute('/login/example'), true)
  assert.equal(isKnownApplicationRoute('/unknown-path'), false)
})

test('returns HTML homepage with merged Vary and security headers', async () => {
  const { response, calls } = await request('/', { headers: { Accept: 'text/html' } })
  assert.equal(response.status, 200)
  assert.equal(response.headers.get('Content-Type'), 'text/html; charset=utf-8')
  assert.match(response.headers.get('Vary'), /Accept-Encoding/)
  assert.match(response.headers.get('Vary'), /Accept/)
  assert.equal(response.headers.get('Cache-Control'), 'no-store')
  assert.equal(response.headers.get('X-Frame-Options'), 'DENY')
  assert.match(await response.text(), /cronos-hero/)
  assert.equal(calls[0].pathname, '/')
})

test('returns the llms file for Markdown homepage requests', async () => {
  const { response } = await request('/', { headers: { Accept: 'text/markdown' } })
  assert.equal(response.status, 200)
  assert.equal(response.headers.get('Content-Type'), 'text/markdown; charset=utf-8')
  assert.equal(await response.text(), '# Cronos')
})

test('passes static assets and known public pages through unchanged', async () => {
  const asset = await request('/assets/main-abc12345.js')
  assert.equal(asset.response.status, 200)
  assert.equal(await asset.response.text(), 'console.log(1)')
  assert.equal(asset.response.headers.get('Cache-Control'), 'public, max-age=31536000, immutable')
  const logo = await request('/logo.png')
  assert.equal(logo.response.headers.get('Content-Type'), 'image/png')
  assert.equal(logo.response.headers.get('Cache-Control'), 'no-cache, max-age=0, must-revalidate')
  const marketingImage = await request('/marketing/hero.webp')
  assert.equal(marketingImage.response.headers.get('Content-Type'), 'image/webp')
  assert.equal(marketingImage.response.headers.get('Cache-Control'), 'no-cache, max-age=0, must-revalidate')
  const page = await request('/about')
  assert.equal(page.response.status, 200)
  assert.equal(await page.response.text(), '<h1>Sobre</h1>')
  assert.equal(page.response.headers.get('Cache-Control'), 'no-store')
})

test('cache-busting queries resolve the same physical public assets', async () => {
  for (const [path, contentType, content] of [
    ['/logo.png?v=20260921', 'image/png', 'png'],
    ['/favicon.png?v=20260921', 'image/png', 'png'],
    ['/marketing/hero.webp?v=20260921', 'image/webp', 'webp'],
  ]) {
    const { response } = await request(path)
    assert.equal(response.status, 200, path)
    assert.equal(response.headers.get('Content-Type'), contentType, path)
    assert.equal(await response.text(), content, path)
    assert.equal(response.headers.get('Cache-Control'), 'no-cache, max-age=0, must-revalidate')
  }
})

test('rewrites every application route family to the application shell', async () => {
  for (const pathname of ['/foundation', '/imports', '/login', '/register', '/login/tasks/choose-organization', '/courses/course-id', '/courses/course-id/classes/class-id', '/courses/course-id/classes/class-id/subjects']) {
    const { response, calls } = await request(pathname)
    assert.equal(response.status, 200, pathname)
    assert.equal(calls.at(-1).pathname, '/app-shell', pathname)
    assert.doesNotMatch(await response.text(), /cronos-hero/)
  }
})

test('returns negotiated 404 bodies for unknown paths', async () => {
  const html = await request('/missing-page')
  assert.equal(html.response.status, 404)
  assert.equal(html.response.headers.get('Content-Type'), 'text/html; charset=utf-8')
  assert.equal(html.response.headers.get('Cache-Control'), 'no-store')
  assert.equal(html.response.headers.get('Location'), null)
  assert.match(await html.response.text(), /Voltar ao início/)
  const markdown = await request('/missing-page', { headers: { Accept: 'text/markdown' } })
  assert.equal(markdown.response.status, 404)
  assert.equal(markdown.response.headers.get('Content-Type'), 'text/markdown; charset=utf-8')
  assert.equal(markdown.response.headers.get('Cache-Control'), 'no-store')
  assert.equal(await markdown.response.text(), '# 404 — Página não encontrada')
})

test('does not cache missing assets', async () => {
  const { response } = await request('/assets/missing-abc12345.js')
  assert.equal(response.status, 404)
  assert.equal(response.headers.get('Cache-Control'), 'no-store')
})

test('removes response bodies for HEAD and never shells unknown unsafe methods', async () => {
  const head = await request('/', { method: 'HEAD' })
  assert.equal(head.response.status, 200)
  assert.equal(await head.response.text(), '')
  const post = await request('/unknown-page', { method: 'POST' })
  assert.equal(post.response.status, 404)
  assert.match(await post.response.text(), /Voltar ao início/)
})
