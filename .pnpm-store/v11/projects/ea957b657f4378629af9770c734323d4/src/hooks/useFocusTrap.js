import { useEffect, useRef } from 'react'

/**
 * useFocusTrap — aprisiona o foco dentro de um elemento (modal, drawer, etc.)
 * para navegação por teclado acessível (WCAG 2.4.3).
 *
 * @param {boolean} active — se true, o foco é aprisionado
 * @param {React.RefObject} containerRef — ref para o elemento contentor
 * @returns {void}
 */
export function useFocusTrap(active, containerRef) {
  const previousActiveElement = useRef(null)

  useEffect(() => {
    if (!active || !containerRef?.current) return

    // Guardar o elemento que tinha foco antes do modal abrir
    previousActiveElement.current = document.activeElement

    // Seletores de elementos focáveis
    const FOCUSABLE = 'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'

    const container = containerRef.current

    // Focar o primeiro elemento focável ou o próprio container
    const firstFocusable = container.querySelector(FOCUSABLE)
    if (firstFocusable) {
      firstFocusable.focus()
    } else {
      container.setAttribute('tabindex', '-1')
      container.focus()
    }

    const handleKeyDown = (e) => {
      if (e.key !== 'Tab') return

      const focusableElements = container.querySelectorAll(FOCUSABLE)
      if (focusableElements.length === 0) return

      const first = focusableElements[0]
      const last = focusableElements[focusableElements.length - 1]

      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault()
          last.focus()
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }

    document.addEventListener('keydown', handleKeyDown)

    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      // Restaurar foco ao elemento original quando o modal fechar
      if (previousActiveElement.current && typeof previousActiveElement.current.focus === 'function') {
        previousActiveElement.current.focus()
      }
    }
  }, [active, containerRef])
}
