import { useMarketingReveal } from '../../hooks/useMarketingReveal'

export default function Reveal({ children, className = '' }) {
  const { elementReference, isVisible } = useMarketingReveal()
  const classes = ['cronos-reveal', isVisible ? 'is-visible' : '', className].filter(Boolean).join(' ')
  return <div ref={elementReference} className={classes}>{children}</div>
}
