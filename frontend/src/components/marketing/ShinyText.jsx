import { memo } from 'react'
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
  const animationDirection = yoyo
    ? direction === 'right' ? 'alternate-reverse' : 'alternate'
    : direction === 'right' ? 'reverse' : 'normal'

  const gradientStyle = disabled ? undefined : {
    '--shiny-angle': `${spread}deg`,
    '--shiny-color': color,
    '--shiny-shine-color': shineColor,
    '--shiny-speed': `${Math.max(speed, 0.1)}s`,
    '--shiny-delay': `${Math.max(delay, 0)}s`,
    '--shiny-animation-direction': animationDirection,
  }

  return (
    <span
      className={`shiny-text ${disabled ? 'shiny-text--disabled' : ''} ${pauseOnHover ? 'shiny-text--pause-on-hover' : ''} ${className}`.trim()}
      style={gradientStyle}
    >
      {text}
    </span>
  )
})

export default ShinyText
