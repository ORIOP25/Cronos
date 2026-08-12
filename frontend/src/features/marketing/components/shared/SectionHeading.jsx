export default function SectionHeading({ eyebrow, title, body, id, align = 'left', variant = 'section', as: Heading = 'h2' }) {
  return (
    <div className={`cronos-section-heading cronos-section-heading--${align} cronos-section-heading--${variant}`}>
      {eyebrow && <p className="cronos-eyebrow">{eyebrow}</p>}
      <Heading id={id}>{title}</Heading>
      {body && <p className="cronos-section-heading__body">{body}</p>}
    </div>
  )
}
