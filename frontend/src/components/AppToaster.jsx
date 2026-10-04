import { useEffect, useState } from 'react'
import { Toaster, ToastBar } from 'react-hot-toast'

const DESKTOP_MEDIA_QUERY = '(min-width: 768px)'
const ERROR_ARIA_PROPS = { role: 'alert', 'aria-live': 'assertive' }

const TOAST_OPTIONS = {
  duration: 4000,
  success: {
    duration: 4000,
    iconTheme: { primary: 'var(--cronos-success)', secondary: 'var(--cronos-surface)' },
  },
  error: {
    duration: 6000,
    iconTheme: { primary: 'var(--cronos-danger)', secondary: 'var(--cronos-surface)' },
  },
  style: {
    maxWidth: 'min(420px, calc(100vw - 32px))',
    padding: '10px 12px',
    border: '1px solid var(--cronos-border)',
    borderRadius: 'var(--cronos-radius-panel)',
    background: 'var(--cronos-surface)',
    color: 'var(--cronos-ink)',
    fontFamily: 'var(--cronos-font-body)',
    boxShadow: 'var(--cronos-shadow-panel)',
  },
}

const CONTAINER_STYLE = {
  top: 'max(16px, env(safe-area-inset-top))',
  left: 'max(16px, env(safe-area-inset-left))',
  right: 'max(16px, env(safe-area-inset-right))',
}

function useDesktopViewport() {
  const [isDesktop, setIsDesktop] = useState(() =>
    typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia(DESKTOP_MEDIA_QUERY).matches)

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return undefined
    const query = window.matchMedia(DESKTOP_MEDIA_QUERY)
    const updatePosition = (event) => setIsDesktop(event.matches)
    query.addEventListener('change', updatePosition)
    return () => query.removeEventListener('change', updatePosition)
  }, [])

  return isDesktop
}

export default function AppToaster() {
  const isDesktop = useDesktopViewport()

  return (
    <Toaster
      position={isDesktop ? 'top-right' : 'top-center'}
      toastOptions={TOAST_OPTIONS}
      containerStyle={CONTAINER_STYLE}
    >
      {(toastItem) => (
        <ToastBar toast={toastItem.type === 'error' ? { ...toastItem, ariaProps: ERROR_ARIA_PROPS } : toastItem} />
      )}
    </Toaster>
  )
}
