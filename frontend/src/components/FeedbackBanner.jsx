import CIcon from '@coreui/icons-react'
import { cilCheckCircle, cilInfo, cilWarning, cilXCircle } from '@coreui/icons'

const TONES = {
  success: { role: 'status', icon: cilCheckCircle },
  danger: { role: 'alert', icon: cilXCircle },
  warning: { role: 'status', icon: cilWarning },
  info: { role: 'status', icon: cilInfo },
}

export default function FeedbackBanner({ tone = 'info', title, children, action }) {
  const { role, icon } = TONES[tone] ?? TONES.info
  return (
    <div className={`feedback-banner feedback-banner--${tone}`} role={role} aria-live={tone === 'danger' ? undefined : 'polite'}>
      <CIcon icon={icon} className="feedback-banner__icon" aria-hidden="true" />
      <div className="feedback-banner__content">
        {title && <p className="feedback-banner__title">{title}</p>}
        <p className="feedback-banner__message">{children}</p>
      </div>
      {action && <div className="feedback-banner__action">{action}</div>}
    </div>
  )
}
