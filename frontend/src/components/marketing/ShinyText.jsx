import { useState, useCallback, useEffect, useRef, memo } from 'react'
import './ShinyText.css'

const ShinyText = memo(function ShinyText({
  text,
  disabled = false,
  speed = 2,
  className = '',
  color = '#3b2415',
  shineColor = '#d4940b',
  spread = 120,
  yoyo = false,
  pauseOnHover = false,
  direction = 'left',
  delay = 0,
}) {
  const [isPaused, setIsPaused] = useState(false)
  const [bgPosition, setBgPosition] = useState('150% center')
  const elapsedRef = useRef(0)
  const lastTimeRef = useRef(null)
  const directionRef = useRef(direction === 'left' ? 1 : -1)

  const animationDuration = speed * 1000
  const delayDuration = delay * 1000

  useEffect(() => {
    directionRef.current = direction === 'left' ? 1 : -1
    elapsedRef.current = 0
  }, [direction])

  useEffect(() => {
    if (disabled || isPaused) {
      lastTimeRef.current = null
      return
    }

    let animationFrameId

    const loop = (time) => {
      if (lastTimeRef.current === null) {
        lastTimeRef.current = time
      } else {
        const deltaTime = time - lastTimeRef.current
        lastTimeRef.current = time
        elapsedRef.current += deltaTime

        let p = 0
        if (yoyo) {
          const cycleDuration = animationDuration + delayDuration
          const fullCycle = cycleDuration * 2
          const cycleTime = elapsedRef.current % fullCycle

          if (cycleTime < animationDuration) {
            const rawP = (cycleTime / animationDuration) * 100
            p = directionRef.current === 1 ? rawP : 100 - rawP
          } else if (cycleTime < cycleDuration) {
            p = directionRef.current === 1 ? 100 : 0
          } else if (cycleTime < cycleDuration + animationDuration) {
            const reverseTime = cycleTime - cycleDuration
            const rawP = 100 - (reverseTime / animationDuration) * 100
            p = directionRef.current === 1 ? rawP : 100 - rawP
          } else {
            p = directionRef.current === 1 ? 0 : 100
          }
        } else {
          const cycleDuration = animationDuration + delayDuration
          const cycleTime = elapsedRef.current % cycleDuration

          if (cycleTime < animationDuration) {
            const rawP = (cycleTime / animationDuration) * 100
            p = directionRef.current === 1 ? rawP : 100 - rawP
          } else {
            p = directionRef.current === 1 ? 100 : 0
          }
        }

        setBgPosition(`${150 - p * 2}% center`)
      }

      animationFrameId = requestAnimationFrame(loop)
    }

    animationFrameId = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(animationFrameId)
  }, [disabled, isPaused, animationDuration, delayDuration, yoyo])

  const handleMouseEnter = useCallback(() => {
    if (pauseOnHover) setIsPaused(true)
  }, [pauseOnHover])

  const handleMouseLeave = useCallback(() => {
    if (pauseOnHover) setIsPaused(false)
  }, [pauseOnHover])

  const gradientStyle = {
    backgroundImage: `linear-gradient(${spread}deg, ${color} 0%, ${color} 20%, ${shineColor} 50%, ${color} 80%, ${color} 100%)`,
    backgroundSize: '200% auto',
    WebkitBackgroundClip: 'text',
    backgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
    backgroundPosition: bgPosition,
  }

  return (
    <span
      className={`shiny-text ${className}`}
      style={disabled ? {} : gradientStyle}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {text}
    </span>
  )
})

export default ShinyText
