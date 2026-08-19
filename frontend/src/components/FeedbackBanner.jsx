const TONE_ROLES = { danger: 'alert', success: 'status', warning: 'status', info: 'status' }

export default function FeedbackBanner({ tone = 'info', title, children, action, onDismiss }) {
  return (
    <div className={`feedback-banner feedback-banner--${tone}`} role={TONE_ROLES[tone] ?? 'status'} aria-live={tone === 'danger' ? undefined : 'polite'}>
      <div className="feedback-banner__content">
        {title && <p className="feedback-banner__title">{title}</p>}
        <p className="feedback-banner__message">{children}</p>
      </div>
      <div className="d-flex align-items-center gap-2">
        {action && <div className="feedback-banner__action">{action}</div>}
        {onDismiss && <button type="button" className="feedback-banner__dismiss" aria-label="Fechar mensagem" onClick={onDismiss}>×</button>}
      </div>
    </div>
  )
}
