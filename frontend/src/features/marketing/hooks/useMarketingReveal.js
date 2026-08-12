import { useEffect, useRef, useState } from 'react'

const observedElements = new Map()
let sharedObserver

function getObserver() {
  if (sharedObserver || typeof IntersectionObserver === 'undefined') return sharedObserver
  sharedObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        const setVisible = observedElements.get(entry.target)
        setVisible?.(true)
        sharedObserver.unobserve(entry.target)
      }
    })
  }, { threshold: 0.12 })
  return sharedObserver
}

export function useMarketingReveal() {
  const elementReference = useRef(null)
  const [isVisible, setIsVisible] = useState(() => typeof IntersectionObserver === 'undefined')

  useEffect(() => {
    const element = elementReference.current
    const observer = getObserver()
    if (!element || !observer) return undefined
    observedElements.set(element, setIsVisible)
    observer.observe(element)
    return () => {
      observedElements.delete(element)
      observer.unobserve(element)
    }
  }, [])

  return { elementReference, isVisible }
}
