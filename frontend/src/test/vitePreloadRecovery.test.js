import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PUBLIC_ASSET_REVISION } from '../utils/publicAsset'
import { registerVitePreloadRecovery, VITE_PRELOAD_RELOAD_KEY } from '../utils/vitePreloadRecovery'

function createWindow() {
  const listeners = new Map()
  const values = new Map()
  return {
    location: { href: 'https://cronos.pt/dashboard?tab=active', replace: vi.fn() },
    sessionStorage: {
      getItem: (key) => values.get(key) ?? null,
      setItem: (key, value) => values.set(key, value),
    },
    addEventListener: (name, handler) => listeners.set(name, handler),
    removeEventListener: (name, handler) => {
      if (listeners.get(name) === handler) listeners.delete(name)
    },
    dispatch: (event) => listeners.get(event.type)?.(event),
  }
}

describe('Vite preload recovery', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('reloads once with a cache-busting marker', () => {
    const windowObject = createWindow()
    const event = { type: 'vite:preloadError', preventDefault: vi.fn() }
    const cleanup = registerVitePreloadRecovery(windowObject)

    windowObject.dispatch(event)
    windowObject.dispatch({ type: 'vite:preloadError', preventDefault: vi.fn() })

    expect(event.preventDefault).toHaveBeenCalledOnce()
    expect(windowObject.location.replace).toHaveBeenCalledOnce()
    expect(windowObject.location.replace).toHaveBeenCalledWith(expect.stringMatching(new RegExp(`cronos-reload=${PUBLIC_ASSET_REVISION}-\\d+`)))
    expect(windowObject.sessionStorage.getItem(VITE_PRELOAD_RELOAD_KEY)).toBe('1')
    cleanup()
  })

  it('leaves the second preload error uncancelled', () => {
    const windowObject = createWindow()
    windowObject.sessionStorage.setItem(VITE_PRELOAD_RELOAD_KEY, '1')
    const event = { type: 'vite:preloadError', preventDefault: vi.fn() }
    registerVitePreloadRecovery(windowObject)

    windowObject.dispatch(event)

    expect(event.preventDefault).not.toHaveBeenCalled()
    expect(windowObject.location.replace).not.toHaveBeenCalled()
  })
})
