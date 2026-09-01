import { useEffect } from 'react'

export function TutorialInteractionGuard({ step, reviewMode }) {
  useEffect(() => {
    const allowedTargets = [...new Set([step.target, ...(step.allowedTargets || [])].filter(Boolean))]
    const targetSelector = allowedTargets.length > 0
      ? allowedTargets.map((target) => `[data-tutorial-target="${target}"]`).join(', ')
      : null
    const entrySelector = step.entryTarget ? `[data-tutorial-target="${step.entryTarget}"]` : null

    const isAllowed = (event) => {
      const target = event.target instanceof Element ? event.target : null
      if (!target) return true
      if (event.type === 'keydown') return true
      if (target.closest('.tutorial-instruction-panel')) return true
      if (target.closest('[role="dialog"]')) return true
      if (reviewMode) return true
      return Boolean(
        (targetSelector && target.closest(targetSelector))
        || (entrySelector && target.closest(entrySelector)),
      )
    }

    const blockUnexpectedInteraction = (event) => {
      if (isAllowed(event)) return
      event.preventDefault()
      event.stopPropagation()
    }

    document.addEventListener('click', blockUnexpectedInteraction, true)
    document.addEventListener('submit', blockUnexpectedInteraction, true)
    return () => {
      document.removeEventListener('click', blockUnexpectedInteraction, true)
      document.removeEventListener('submit', blockUnexpectedInteraction, true)
    }
  }, [reviewMode, step])

  return null
}
