import { CButton, CButtonGroup } from '@coreui/react'
import FeedbackBanner from '../FeedbackBanner'

const PROPOSAL_PREVIEW_NOTICE = 'Está a ver a proposta pendente. Nada muda no horário publicado até a aprovar.'

const ProposalPreviewToggle = ({ showingProposal, onChange }) => (
  <div className="p-3 border-bottom d-flex flex-column gap-2">
    <CButtonGroup size="sm" aria-label="Horário a mostrar">
      <CButton
        color={showingProposal ? 'outline-secondary' : 'primary'}
        aria-pressed={!showingProposal}
        onClick={() => onChange(false)}
      >
        Horário publicado
      </CButton>
      <CButton
        color={showingProposal ? 'primary' : 'outline-secondary'}
        aria-pressed={showingProposal}
        onClick={() => onChange(true)}
      >
        Proposta pendente
      </CButton>
    </CButtonGroup>
    {showingProposal && <FeedbackBanner tone="info">{PROPOSAL_PREVIEW_NOTICE}</FeedbackBanner>}
  </div>
)

export default ProposalPreviewToggle
