import React from 'react'
import { Link } from 'react-router-dom'
import { CreateOrganization } from '@clerk/react'
import BrandPanel from '../components/auth/BrandPanel'
import {
  BRAND_STATS_CREATEORG,
  BRAND_TAGLINE_CREATEORG,
  CLERK_APPEARANCE_AUTH,
} from '../utils/authDesign'

export default function CreateOrgPage() {
  return (
    <div className="zen-auth-page">
      <div className="zen-auth-layout">
        <BrandPanel tagline={BRAND_TAGLINE_CREATEORG} stats={BRAND_STATS_CREATEORG} />

        <div className="zen-auth-form-side">
          <div className="zen-auth-form-side-geo">
            <div className="zen-auth-form-side-line-1" />
            <div className="zen-auth-form-side-line-2" />
            <div className="zen-auth-form-side-dot zen-auth-form-side-dot-1" />
            <div className="zen-auth-form-side-dot zen-auth-form-side-dot-2" />
          </div>

          <div className="zen-auth-form-wrapper">
            <CreateOrganization
              routing="path"
              path="/create-org"
              afterCreateOrganizationUrl="/onboarding"
              skipInvitationScreen={true}
              appearance={CLERK_APPEARANCE_AUTH}
            />

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
