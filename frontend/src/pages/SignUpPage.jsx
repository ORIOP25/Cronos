import { Link } from 'react-router-dom'
import { SignUp } from '@clerk/react'
import BrandPanel from '../components/auth/BrandPanel'
import {
  BRAND_STATS_REGISTER,
  BRAND_TAGLINE_REGISTER,
  CLERK_APPEARANCE_AUTH,
} from '../utils/authDesign'

export default function SignUpPage() {
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
            <SignUp
              routing="path"
              path="/register"
              signInUrl="/login"
              afterSignUpUrl="/create-org"
              appearance={CLERK_APPEARANCE_AUTH}
            />

            <p className="zen-auth-legal-links">
              Ao criar uma conta, consulte os <Link to="/termos">Termos de Serviço</Link> e a <Link to="/privacidade">Política de Privacidade</Link>.
            </p>

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
