import { useState } from 'react'
import { toast } from 'react-hot-toast'
import {
  CButton,
  CModal,
  CModalBody,
  CModalFooter,
  CModalHeader,
  CModalTitle,
  CSpinner,
} from '@coreui/react'
import AvailabilityGrid from './AvailabilityGrid'
import AvailabilityToolbar from './AvailabilityToolbar'
import FeedbackBanner from './FeedbackBanner'
import StatePanel from './StatePanel'
import { getApiErrorMessage, isApiErrorTransient } from '../utils/apiErrors'
import { useAttemptScope } from '../hooks/useAttemptScope'
import { useAvailabilityDraft } from '../hooks/useAvailabilityDraft'

/**
 * Shared weekly availability editor: loading, error and empty states, the
 * toolbar, the grid, the footer and the save flow. Teacher and class modals
 * configure it, so both behave the same without duplicating the window.
 *
 * `footerStart` may be a node or a function of `{ isDirty, changedCount }` so a
 * caller can disable an extra action while there are unsaved changes.
 */
export default function AvailabilityEditorModal({
  title,
  intro,
  onDate,
  timeslots,
  rows,
  isLoading,
  isError,
  isSaving,
  onSave,
  onClose,
  successMessage,
  saveLabel = 'Guardar disponibilidade',
  footerStart,
  bodyOverride,
  footerOverride,
}) {
  const [blockMessage, setBlockMessage] = useState('')
  const attemptScope = useAttemptScope()
  const draft = useAvailabilityDraft({ timeslots, rows, disabled: isSaving })

  const handleSave = async () => {
    if (!draft.isDirty || isSaving) return
    setBlockMessage('')
    const attempt = attemptScope.capture()
    const payload = draft.buildPayload()
    try {
      await onSave(payload)
      if (!attemptScope.isCurrent(attempt)) return
      draft.reset()
      toast.success(successMessage)
    } catch (error) {
      if (!attemptScope.isCurrent(attempt)) return
      const message = getApiErrorMessage(error, 'Não foi possível guardar a disponibilidade.')
      if (isApiErrorTransient(error)) toast.error(message)
      else setBlockMessage(message)
    }
  }

  const footerStartNode = typeof footerStart === 'function'
    ? footerStart({ isDirty: draft.isDirty, changedCount: draft.changedCount })
    : footerStart

  return (
    <CModal
      visible
      size="xl"
      onClose={isSaving ? undefined : onClose}
      backdrop="static"
      keyboard={!isSaving}
      scrollable
      className="confirmation-modal"
    >
      <CModalHeader onClose={isSaving ? undefined : onClose}>
        <CModalTitle>{title}</CModalTitle>
      </CModalHeader>
      <CModalBody>
        {intro && <p className="small text-muted">{intro}</p>}
        {blockMessage && <div className="mb-3"><FeedbackBanner tone="danger">{blockMessage}</FeedbackBanner></div>}
        {onDate && <p className="small">Grelha válida em {onDate.split('-').reverse().join('/')}.</p>}
        {bodyOverride || (
          isLoading || isError ? (
            <>
              {isLoading && <StatePanel state="loading" title="A carregar disponibilidade" compact />}
              {!isLoading && isError && (
                <StatePanel
                  state="error"
                  title="Não foi possível carregar a grelha"
                  description="Verifique a ligação e tente novamente."
                  compact
                />
              )}
            </>
          ) : !timeslots.length ? (
            <StatePanel
              state="empty"
              title="A escola ainda não configurou blocos"
              description="A disponibilidade fica disponível depois de a grelha horária ser configurada."
              compact
            />
          ) : (
            <>
              <AvailabilityToolbar
                selectedScore={draft.selectedScore}
                onSelect={draft.setSelectedScore}
                changedCount={draft.changedCount}
                disabled={isSaving}
              />
              <AvailabilityGrid
                timeslots={timeslots}
                availabilityMap={draft.draftMap}
                onChange={draft.handleGridChange}
                selectedMode={draft.selectedScore}
              />
            </>
          )
        )}
      </CModalBody>
      <CModalFooter>
        {footerOverride || (
          <>
            {footerStartNode}
            <CButton color="secondary" variant="outline" onClick={onClose} disabled={isSaving}>
              Fechar
            </CButton>
            <CButton color="primary" onClick={() => { void handleSave() }} disabled={!draft.isDirty || isSaving}>
              {isSaving ? <><CSpinner size="sm" className="me-1" />A guardar…</> : saveLabel}
            </CButton>
          </>
        )}
      </CModalFooter>
    </CModal>
  )
}
