import { useState } from 'react'
import { SignUp, useAuth } from '@clerk/react'
import { Link, useLocation } from 'react-router-dom'
import BrandPanel from '../components/auth/BrandPanel'
import { hasLegalAcceptance, setLegalAcceptance } from '../features/legal/acceptanceStorage'
import {
  BRAND_STATS_REGISTER,
  BRAND_TAGLINE_REGISTER,
  CLERK_APPEARANCE_AUTH,
} from '../utils/authDesign'

export default function SignUpPage() {
  const { userId } = useAuth()
  const location = useLocation()
  const isChooseOrganizationTask = location.pathname.endsWith('/tasks/choose-organization')
  const [acceptedByClick, setAcceptedByClick] = useState(false)
  const legalAccepted = hasLegalAcceptance(userId) || acceptedByClick

  function handleLegalChange(event) {
    const nextAccepted = event.target.checked
    setAcceptedByClick(nextAccepted)
    setLegalAcceptance(userId, nextAccepted)
  }

  function blockTaskActionUntilAccepted(event) {
    if (legalAccepted) return
    const target = event.target instanceof Element ? event.target : null
    const isSubmit = event.type === 'submit'
    const isButtonAction = target?.closest('button, [role="button"]')
    if (!isSubmit && !isButtonAction) return
    event.preventDefault()
    event.stopPropagation()
  }

  return (
    <div className="zen-auth-page">
      <div className="zen-auth-layout">
        <BrandPanel tagline={BRAND_TAGLINE_REGISTER} stats={BRAND_STATS_REGISTER} />

        <div className="zen-auth-form-side">
          <div className="zen-auth-form-side-geo">
            <div className="zen-auth-form-side-line-1" />
            <div className="zen-auth-form-side-line-2" />
            <div className="zen-auth-form-side-dot zen-auth-form-side-dot-1" />
            <div className="zen-auth-form-side-dot zen-auth-form-side-dot-2" />
          </div>

          <div className="zen-auth-form-wrapper">
            <div
              onClickCapture={isChooseOrganizationTask ? blockTaskActionUntilAccepted : undefined}
              onSubmitCapture={isChooseOrganizationTask ? blockTaskActionUntilAccepted : undefined}
            >
              <SignUp
                routing="path"
                path="/register"
                signInUrl="/login"
                afterSignUpUrl="/create-org"
                appearance={CLERK_APPEARANCE_AUTH}
              />
            </div>

            {isChooseOrganizationTask ? (
              <TaskLegalAcceptance accepted={legalAccepted} onChange={handleLegalChange} />
            ) : (
              <p className="zen-auth-legal-links">
                Ao criar uma conta, concorda com os <Link to="/termos">Termos de Serviço</Link> e a <Link to="/privacidade">Política de Privacidade</Link>.
              </p>
            )}

            <div className="zen-auth-form-footer">
              <Link to="/" className="zen-auth-back-link">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M10 4 L6 8 L10 12" />
                </svg>
                Voltar ao início
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function TaskLegalAcceptance({ accepted, onChange }) {
  return (
    <label className="zen-auth-legal-checkbox">
      <input type="checkbox" checked={accepted} onChange={onChange} />
      <span>
        Li e concordo com os <Link to="/termos" target="_blank" rel="noreferrer">Termos de Serviço</Link> e a <Link to="/privacidade" target="_blank" rel="noreferrer">Política de Privacidade</Link>.
      </span>
    </label>
  )
}
