import { Link } from 'react-router-dom'
import { SignIn } from '@clerk/react'
import BrandPanel from '../components/auth/BrandPanel'
import {
  BRAND_STATS_LOGIN,
  BRAND_TAGLINE_LOGIN,
  CLERK_APPEARANCE_AUTH,
} from '../utils/authDesign'

export default function SignInPage() {
  return (
    <div className="zen-auth-page zen-auth-page--login">
      <div className="zen-auth-layout">
        <BrandPanel tagline={BRAND_TAGLINE_LOGIN} stats={BRAND_STATS_LOGIN} />

        <div className="zen-auth-form-side">
          <div className="zen-auth-form-side-geo">
            <div className="zen-auth-form-side-line-1" />
            <div className="zen-auth-form-side-line-2" />
            <div className="zen-auth-form-side-dot zen-auth-form-side-dot-1" />
            <div className="zen-auth-form-side-dot zen-auth-form-side-dot-2" />
          </div>

          <div className="zen-auth-form-wrapper">
            <SignIn
              routing="path"
              path="/login"
              signUpUrl="/register"
              fallbackRedirectUrl="/"
              appearance={CLERK_APPEARANCE_AUTH}
            />

            <div className="zen-auth-recovery-help">
              <p>
                Já tem conta ou o convite não chegou? O convite não define uma
                palavra-passe. Pode <strong>entrar com Google</strong> usando o mesmo
                email.
              </p>
              <Link to="/recuperar-palavra-passe" className="zen-auth-recovery-link">
                Recuperar palavra-passe
              </Link>
            </div>

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
