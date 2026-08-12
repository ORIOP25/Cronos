export default function MarketingSection({ as: Element = 'section', className = '', labelledBy, children, ...props }) {
  const classes = ['cronos-marketing-section', className].filter(Boolean).join(' ')
  return <Element className={classes} aria-labelledby={labelledBy} {...props}>{children}</Element>
}
