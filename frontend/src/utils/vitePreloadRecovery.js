import { PUBLIC_ASSET_REVISION } from './publicAsset'

export const VITE_PRELOAD_RELOAD_KEY = 'cronos:vite-preload-reloaded'

export function registerVitePreloadRecovery(windowObject = window) {
  const handlePreloadError = (event) => {
    let storage
    try {
      storage = windowObject.sessionStorage
      if (storage.getItem(VITE_PRELOAD_RELOAD_KEY)) return
      storage.setItem(VITE_PRELOAD_RELOAD_KEY, '1')
    } catch (error) {
      windowObject.console?.warn('Unable to persist Vite preload recovery marker.', error)
      return
    }

    event.preventDefault()
    const url = new URL(windowObject.location.href)
    url.searchParams.set('cronos-reload', `${PUBLIC_ASSET_REVISION}-${Date.now()}`)
    windowObject.location.replace(url.toString())
  }

  windowObject.addEventListener('vite:preloadError', handlePreloadError)
  return () => windowObject.removeEventListener('vite:preloadError', handlePreloadError)
}
