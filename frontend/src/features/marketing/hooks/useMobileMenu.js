import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'

export function useMobileMenu() {
  const [isOpen, setIsOpen] = useState(false)
  const toggleReference = useRef(null)
  const location = useLocation()

  const closeMenu = useCallback(() => setIsOpen(false), [])
  const closeMenuAndRestoreFocus = useCallback(() => {
    setIsOpen(false)
    window.requestAnimationFrame(() => toggleReference.current?.focus())
  }, [])

  const toggleMenu = useCallback(() => setIsOpen((current) => !current), [])

  useEffect(() => {
    const closeTimer = window.setTimeout(() => setIsOpen(false), 0)
    return () => window.clearTimeout(closeTimer)
  }, [closeMenu, location.pathname])

  useEffect(() => {
    if (!isOpen) return undefined

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') closeMenuAndRestoreFocus()
    }
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    document.addEventListener('keydown', handleKeyDown)

    return () => {
      document.body.style.overflow = previousOverflow
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [closeMenuAndRestoreFocus, isOpen])

  return { isOpen, toggleReference, toggleMenu, closeMenu, closeMenuAndRestoreFocus }
}
