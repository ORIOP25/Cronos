import { useEffect } from 'react'

export function TutorialInteractionGuard({ step, reviewMode, onTargetAction }) {
  useEffect(() => {
    const selector = step.target ? `[data-tutorial-target="${step.target}"]` : null

    const isAllowed = (event) => {
      if (event.target.closest('.tutorial-instruction-panel')) return true
      if (reviewMode || step.kind !== 'exercise' || !step.target) return false
      const dialog = document.querySelector('[role="dialog"]')
      const allowed = dialog || document.querySelector(selector)
      return Boolean(allowed?.contains(event.target))
    }
    const blockUnexpectedInteraction = (event) => {
      if (isAllowed(event)) return
      event.preventDefault()
      event.stopPropagation()
    }
    const completeInteractionStep = (event) => {
      if (reviewMode || step.completion !== 'interaction' || !selector) return
      if (!event.target.closest(selector)) return
      window.setTimeout(() => onTargetAction?.(), 0)
    }
    document.addEventListener('click', blockUnexpectedInteraction, true)
    document.addEventListener('submit', blockUnexpectedInteraction, true)
    document.addEventListener('keydown', blockUnexpectedInteraction, true)
    document.addEventListener('click', completeInteractionStep, true)
    return () => {
      document.removeEventListener('click', blockUnexpectedInteraction, true)
      document.removeEventListener('submit', blockUnexpectedInteraction, true)
      document.removeEventListener('keydown', blockUnexpectedInteraction, true)
      document.removeEventListener('click', completeInteractionStep, true)
    }
  }, [onTargetAction, reviewMode, step])

  return null
}
