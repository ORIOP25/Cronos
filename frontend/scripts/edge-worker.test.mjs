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
  ['/sobre', { body: '<h1>Sobre</h1>', contentType: 'text/html; charset=utf-8', etag: '"sobre-v1"' }],
  ['/about', { body: '<h1>Sobre</h1>', contentType: 'text/html; charset=utf-8' }],
  ['/assets/main-abc12345.js', { body: 'console.log(1)', contentType: 'text/javascript', etag: '"main-abc12345"' }],
  ['/logo.png', { body: 'png', contentType: 'image/png', etag: '"logo-v1"', lastModified: 'Wed, 21 Sep 2026 00:00:00 GMT' }],
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
          const headers = { 'Content-Type': asset.contentType, ...(url.pathname === '/' ? { Vary: 'Accept-Encoding' } : {}) }
          if (asset.etag) headers.ETag = asset.etag
          if (asset.lastModified) headers['Last-Modified'] = asset.lastModified
          if (asset.etag && request.headers.get('If-None-Match') === asset.etag) {
            return Promise.resolve(new Response(null, { status: 304, headers }))
          }
          if (asset.lastModified && request.headers.get('If-Modified-Since') === asset.lastModified) {
            return Promise.resolve(new Response(null, { status: 304, headers }))
          }
          return Promise.resolve(new Response(asset.body, { headers }))
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

test('prefers HTML when the client gives it a higher quality value', () => {
  assert.equal(acceptsMarkdown('text/html;q=1,text/markdown;q=0.1'), false)
  assert.equal(acceptsMarkdown('text/html;q=0.9,text/markdown;q=0.8'), false)
  assert.equal(acceptsMarkdown('application/xhtml+xml;q=1,text/markdown;q=0.5'), false)
})

test('selects Markdown only when the client prefers it', () => {
  assert.equal(acceptsMarkdown('text/markdown'), true)
  assert.equal(acceptsMarkdown('text/markdown, text/html;q=0.9'), true)
  assert.equal(acceptsMarkdown('text/markdown;q=0.9,*/*;q=0.1'), true)
})

test('resolves equal quality values deterministically', () => {
  assert.equal(acceptsMarkdown('text/html;q=1,text/markdown;q=1'), false)
  assert.equal(acceptsMarkdown('text/markdown;q=1,*/*;q=1'), true)
})

test('rejects q=0, malformed, and out-of-range Markdown quality values', () => {
  assert.equal(acceptsMarkdown('text/markdown;q=0, text/html;q=1'), false)
  assert.equal(acceptsMarkdown('text/markdown;q=2'), false)
  assert.equal(acceptsMarkdown('text/markdown;q=-1'), false)
  assert.equal(acceptsMarkdown('text/markdown;q=abc'), false)
  assert.equal(acceptsMarkdown('text/markdown;q=1.5,text/html;q=0.5'), false)
})

test('rejects JavaScript number formats that are not valid HTTP quality values', () => {
  assert.equal(acceptsMarkdown('text/markdown;q=1e0,text/html;q=0.5'), false)
  assert.equal(acceptsMarkdown('text/markdown;q=0x1,text/html;q=0.5'), false)
  assert.equal(acceptsMarkdown('text/markdown;q=1.0000'), false)
  assert.equal(acceptsMarkdown('text/markdown;q=0.1234'), false)
  assert.equal(acceptsMarkdown('text/markdown;q=.5'), false)
})

test('applies wildcard fallback to each supported HTML alternative', () => {
  assert.equal(acceptsMarkdown('text/markdown;q=0.5,application/xhtml+xml;q=0.1,text/*;q=1'), false)
  assert.equal(acceptsMarkdown('text/markdown;q=0.5,text/*;q=1'), false)
  assert.equal(acceptsMarkdown('text/markdown;q=0.5,application/*;q=1'), false)
  assert.equal(acceptsMarkdown('text/markdown;q=1,text/*;q=0.5'), true)
  assert.equal(acceptsMarkdown('text/markdown;q=1,text/*;q=1'), true)
  assert.equal(acceptsMarkdown('text/markdown;q=1,text/html;q=0'), true)
})

test('treats missing, wildcard, and non-Markdown headers as HTML', () => {
  assert.equal(acceptsMarkdown(''), false)
  assert.equal(acceptsMarkdown('*/*'), false)
  assert.equal(acceptsMarkdown('text/html'), false)
  assert.equal(acceptsMarkdown('text/html, */*;q=0.8'), false)
})

test('parses Markdown acceptance case-insensitively with surrounding whitespace', () => {
  assert.equal(acceptsMarkdown('  TEXT/MARKDOWN ; Q=1 , text/html;q=0.5 '), true)
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

test('serves the HTML homepage when HTML outranks Markdown for GET and HEAD', async () => {
  const html = await request('/', { headers: { Accept: 'text/html;q=1,text/markdown;q=0.1' } })
  assert.equal(html.response.status, 200)
  assert.equal(html.response.headers.get('Content-Type'), 'text/html; charset=utf-8')
  assert.match(html.response.headers.get('Vary'), /Accept/)
  assert.match(await html.response.text(), /cronos-hero/)

  const head = await request('/', { method: 'HEAD', headers: { Accept: 'text/html;q=1,text/markdown;q=0.1' } })
  assert.equal(head.response.status, 200)
  assert.equal(head.response.headers.get('Content-Type'), 'text/html; charset=utf-8')
  assert.equal(await head.response.text(), '')
})

test('negotiates 404 bodies from the same preference without masking the status', async () => {
  const html = await request('/missing-page', { headers: { Accept: 'text/html;q=1,text/markdown;q=0.1' } })
  assert.equal(html.response.status, 404)
  assert.equal(html.response.headers.get('Content-Type'), 'text/html; charset=utf-8')
  assert.equal(html.response.headers.get('Cache-Control'), 'no-store')
  assert.match(await html.response.text(), /Voltar ao início/)

  const head = await request('/missing-page', { method: 'HEAD', headers: { Accept: 'text/html;q=1,text/markdown;q=0.1' } })
  assert.equal(head.response.status, 404)
  assert.equal(head.response.headers.get('Content-Type'), 'text/html; charset=utf-8')
  assert.equal(await head.response.text(), '')

  const excluded = await request('/missing-page', { headers: { Accept: 'text/markdown;q=0,text/html;q=1' } })
  assert.equal(excluded.response.status, 404)
  assert.equal(excluded.response.headers.get('Content-Type'), 'text/html; charset=utf-8')
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

test('preserves conditional 304 revalidation for existing static assets', async () => {
  const asset = await request('/assets/main-abc12345.js', { headers: { 'If-None-Match': '"main-abc12345"' } })
  assert.equal(asset.response.status, 304)
  assert.equal(await asset.response.text(), '')
  assert.equal(asset.response.headers.get('ETag'), '"main-abc12345"')
  assert.equal(asset.response.headers.get('Cache-Control'), 'public, max-age=31536000, immutable')
  assert.equal(asset.response.headers.get('X-Frame-Options'), 'DENY')
  assert.equal(asset.response.headers.get('X-Content-Type-Options'), 'nosniff')

  const strippedQuery = await request('/assets/main-abc12345.js?v=20260921', { headers: { 'If-None-Match': '"main-abc12345"' } })
  assert.equal(strippedQuery.response.status, 304)
  assert.equal(await strippedQuery.response.text(), '')

  const lastModified = await request('/logo.png', { headers: { 'If-Modified-Since': 'Wed, 21 Sep 2026 00:00:00 GMT' } })
  assert.equal(lastModified.response.status, 304)
  assert.equal(lastModified.response.headers.get('Last-Modified'), 'Wed, 21 Sep 2026 00:00:00 GMT')
  assert.equal(lastModified.response.headers.get('Cache-Control'), 'no-cache, max-age=0, must-revalidate')

  const head = await request('/assets/main-abc12345.js', { method: 'HEAD', headers: { 'If-None-Match': '"main-abc12345"' } })
  assert.equal(head.response.status, 304)
  assert.equal(await head.response.text(), '')
})

test('preserves conditional 304 revalidation for known public HTML routes', async () => {
  const { response } = await request('/sobre', { headers: { 'If-None-Match': '"sobre-v1"' } })
  assert.equal(response.status, 304)
  assert.equal(await response.text(), '')
  assert.equal(response.headers.get('ETag'), '"sobre-v1"')
  assert.equal(response.headers.get('Cache-Control'), 'no-store')
  assert.equal(response.headers.get('X-Frame-Options'), 'DENY')
})

test('keeps missing assets at 404 no-store under conditional revalidation', async () => {
  const { response } = await request('/assets/missing-abc12345.js', { headers: { 'If-None-Match': '"main-abc12345"' } })
  assert.equal(response.status, 404)
  assert.equal(response.headers.get('Cache-Control'), 'no-store')
  assert.match(await response.text(), /Voltar ao início/)
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
