const PUBLIC_ROUTES = new Set([
  '/',
  '/vantagens',
  '/como-funciona',
  '/sobre',
  '/ajuda',
  '/contacto',
  '/privacidade',
  '/termos',
  '/dpa',
  '/cookies',
  '/about',
  '/contact',
  '/privacy',
])

const APPLICATION_ROUTES = new Set([
  '/dashboard',
  '/imports',
  '/members',
  '/rooms',
  '/subjects',
  '/courses',
  '/config',
  '/schedules',
  '/absences',
  '/timesheets',
  '/my-schedules',
  '/my-progress',
  '/my-availability',
  '/foundation',
  '/foundation/waiting',
  '/guide',
  '/recuperar-palavra-passe',
])

const AUTH_ROUTE_PATTERN = /^\/(?:login|register|sign-in|sign-up)(?:\/.*)?$/
const COURSE_ROUTE_PATTERNS = [
  /^\/courses\/[^/]+$/,
  /^\/courses\/[^/]+\/classes\/[^/]+$/,
  /^\/courses\/[^/]+\/classes\/[^/]+\/subjects$/,
]

const SECURITY_HEADERS = {
  'Content-Security-Policy': "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; script-src 'self' https://clerk.cronos.pt https://challenges.cloudflare.com https://*.protect.clerk.com; connect-src 'self' https://api.cronos.pt https://clerk.cronos.pt https://*.protect.clerk.com https://challenges.cloudflare.com; img-src 'self' data: https://img.clerk.com; font-src 'self' data:; style-src 'self' 'unsafe-inline'; worker-src 'self' blob:; frame-src 'self' https://challenges.cloudflare.com https://*.protect.clerk.com; upgrade-insecure-requests",
  'X-Frame-Options': 'DENY',
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
  'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
  'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
}

const CACHE_CONTROL = {
  noStore: 'no-store',
  publicAsset: 'no-cache, max-age=0, must-revalidate',
  hashedAsset: 'public, max-age=31536000, immutable',
}

export function normalizePathname(pathname) {
  return pathname.length > 1 ? pathname.replace(/\/$/, '') : pathname
}

function qualityValue(parameters) {
  const match = parameters.match(/(?:^|;)\s*q\s*=\s*([0-9.]+)/i)
  return match ? Number(match[1]) : 1
}

export function acceptsMarkdown(acceptHeader = '') {
  for (const value of acceptHeader.split(',')) {
    const [mediaType, ...parameters] = value.trim().toLowerCase().split(';')
    if (mediaType !== 'text/markdown') continue
    const quality = qualityValue(parameters.join(';'))
    if (quality > 0) return true
  }
  return false
}

export function isKnownApplicationRoute(pathname) {
  const normalizedPath = normalizePathname(pathname)
  return APPLICATION_ROUTES.has(normalizedPath)
    || AUTH_ROUTE_PATTERN.test(normalizedPath)
    || COURSE_ROUTE_PATTERNS.some((pattern) => pattern.test(normalizedPath))
}

function isStaticAssetPath(pathname) {
  return pathname.includes('.') || pathname === '/llms.txt' || pathname === '/robots.txt' || pathname === '/sitemap.xml'
}

function isPublicAssetPath(pathname) {
  return pathname === '/logo.png'
    || pathname === '/og-cronos.png'
    || /^\/favicon\.[^/]+$/.test(pathname)
    || pathname.startsWith('/marketing/')
}

function assetCacheControl(pathname) {
  if (pathname.startsWith('/assets/')) return CACHE_CONTROL.hashedAsset
  if (isPublicAssetPath(pathname)) return CACHE_CONTROL.publicAsset
  return CACHE_CONTROL.noStore
}

function mergeVary(existingValue, requiredValue) {
  const values = (existingValue || '').split(',').map((value) => value.trim()).filter(Boolean)
  if (!values.some((value) => value.toLowerCase() === requiredValue.toLowerCase())) values.push(requiredValue)
  return values.join(', ')
}

export function withWorkerHeaders(response, { contentType, status, vary, cacheControl } = {}, method = 'GET') {
  const headers = new Headers(response.headers)
  for (const [name, value] of Object.entries(SECURITY_HEADERS)) headers.set(name, value)
  if (contentType) headers.set('Content-Type', contentType)
  if (vary) headers.set('Vary', mergeVary(headers.get('Vary'), vary))
  if (cacheControl) headers.set('Cache-Control', cacheControl)
  return new Response(method === 'HEAD' ? null : response.body, {
    status: status ?? response.status,
    statusText: response.statusText,
    headers,
  })
}

function assetRequest(request, pathname) {
  const url = new URL(request.url)
  url.pathname = pathname
  url.search = ''
  return new Request(url, request)
}

async function fetchAsset(env, request, pathname) {
  return env.ASSETS.fetch(assetRequest(request, pathname))
}

async function notFoundResponse(env, request, markdown) {
  const assetPath = markdown ? '/404.md' : '/404'
  const response = await fetchAsset(env, request, assetPath)
  return withWorkerHeaders(response, {
    contentType: markdown ? 'text/markdown; charset=utf-8' : 'text/html; charset=utf-8',
    status: 404,
    vary: 'Accept',
    cacheControl: CACHE_CONTROL.noStore,
  }, request.method)
}

async function handleRequest(request, env) {
  const url = new URL(request.url)
  const pathname = normalizePathname(url.pathname)
  const markdown = acceptsMarkdown(request.headers.get('Accept') || '')
  const method = request.method.toUpperCase()

  if (pathname === '/') {
    if (method !== 'GET' && method !== 'HEAD') return notFoundResponse(env, request, false)
    // Cloudflare Pages canonicalizes `/index.html` to `/`. Asking Assets for
    // the file path here would return a self-redirect (`308 Location: /`),
    // which makes the homepage impossible for crawlers to fetch.
    const response = await fetchAsset(env, request, markdown ? '/llms.txt' : '/')
    return withWorkerHeaders(response, {
      contentType: markdown ? 'text/markdown; charset=utf-8' : 'text/html; charset=utf-8',
      vary: 'Accept',
      cacheControl: CACHE_CONTROL.noStore,
    }, method)
  }

  if (method !== 'GET' && method !== 'HEAD') return notFoundResponse(env, request, markdown)

  const assetResponse = await fetchAsset(env, request, pathname)
  const isPublicRoute = PUBLIC_ROUTES.has(pathname)
  // A conditional revalidation (`If-None-Match`/`If-Modified-Since`) legitimately
  // yields 304, which is not `ok`. Pass it through for real route/asset paths so
  // clients keep their cached bytes instead of receiving the HTML 404 document.
  const assetServed = assetResponse.ok || assetResponse.status === 304
  if (assetServed && (isPublicRoute || isStaticAssetPath(pathname))) {
    return withWorkerHeaders(assetResponse, {
      cacheControl: isPublicRoute ? CACHE_CONTROL.noStore : assetCacheControl(pathname),
    }, method)
  }

  if (isKnownApplicationRoute(pathname)) {
    const shell = await fetchAsset(env, request, '/app-shell')
    return withWorkerHeaders(shell, {
      contentType: 'text/html; charset=utf-8',
      cacheControl: CACHE_CONTROL.noStore,
    }, method)
  }

  return notFoundResponse(env, request, markdown)
}

export default {
  fetch: handleRequest,
}
