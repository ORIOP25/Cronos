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
import { TXT } from '../utils/terminology'

/**
 * Shared weekly availability editor: loading, error and empty states, the
 * toolbar, the grid, the footer and the save flow. Teacher and class modals
 * configure it, so both behave the same without duplicating the window.
 *
 * `footerStart` may be a node or a function of `{ isDirty, changedCount }` so a
 * caller can disable an extra action while there are unsaved changes.
 *
 * `beforeGrid` renders an extra section above the grid.
 * `extraPart` is an optional second dirty part saved in its own request:
 * `{ isDirty, save, reset, failureMessage, savedMessage }`. Each part becomes
 * clean when its own request succeeds, even if the other part fails.
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
  beforeGrid,
  extraPart,
  gridMessages = { failureMessage: 'A grelha não foi guardada.', savedMessage: 'A grelha ficou guardada.' },
}) {
  const [blockMessage, setBlockMessage] = useState('')
  const attemptScope = useAttemptScope()
  const draft = useAvailabilityDraft({ timeslots, rows, disabled: isSaving })
  const extraDirty = Boolean(extraPart?.isDirty)

  const handleSave = async () => {
    if ((!draft.isDirty && !extraDirty) || isSaving) return
    setBlockMessage('')
    const attempt = attemptScope.capture()

    let extraError = null
    if (extraDirty) {
      try {
        await extraPart.save()
      } catch (error) {
        extraError = error
      }
      if (!attemptScope.isCurrent(attempt)) return
      if (!extraError) extraPart.reset()
    }

    let gridError = null
    if (draft.isDirty) {
      try {
        await onSave(draft.buildPayload())
      } catch (error) {
        gridError = error
      }
      if (!attemptScope.isCurrent(attempt)) return
      if (!gridError) draft.reset()
    }

    if (!extraError && !gridError) {
      toast.success(successMessage)
      return
    }

    // A single grid failure keeps the existing class-modal feedback contract.
    if (!extraDirty) {
      const message = getApiErrorMessage(gridError, 'Não foi possível guardar a disponibilidade.')
      if (isApiErrorTransient(gridError)) toast.error(message)
      else setBlockMessage(message)
      return
    }

    const parts = []
    if (extraDirty) parts.push(extraError ? extraPart.failureMessage : extraPart.savedMessage)
    if (draft.isDirty) parts.push(gridError ? gridMessages.failureMessage : gridMessages.savedMessage)
    setBlockMessage([...parts, 'Tente novamente.'].join(' '))
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
        {beforeGrid && <div className="mb-3">{beforeGrid}</div>}
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
              description="A disponibilidade aparece depois de configurar a grelha horária."
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
              {draft.isDirty || extraDirty ? TXT.CANCEL : TXT.CLOSE}
            </CButton>
            <CButton color="primary" onClick={() => { void handleSave() }} disabled={(!draft.isDirty && !extraDirty) || isSaving}>
              {isSaving ? <><CSpinner size="sm" className="me-1" />A guardar…</> : saveLabel}
            </CButton>
          </>
        )}
      </CModalFooter>
    </CModal>
  )
}
