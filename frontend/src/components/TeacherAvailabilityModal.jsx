import { useMemo, useState } from 'react'
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
import { useTimeslots } from '../features/catalog/data'
import { useSaveTeacherAvailability, useTeacherAvailability } from '../features/operations/data'
import { getApiErrorMessage, isApiErrorTransient } from '../utils/apiErrors'
import { useAttemptScope } from '../hooks/useAttemptScope'
import { useAvailabilityDraft } from '../hooks/useAvailabilityDraft'

/**
 * Direção edita a disponibilidade de um professor, incluindo quem não tem acesso.
 */
export default function TeacherAvailabilityModal({ teacher, onDate, onClose }) {
  const [blockMessage, setBlockMessage] = useState('')
  const timeslotsQuery = useTimeslots({ onDate })
  const availabilityQuery = useTeacherAvailability({ teacherId: teacher?.id, onDate })
  const saveMutation = useSaveTeacherAvailability()
  const isSaving = saveMutation.isPending
  const attemptScope = useAttemptScope()
  const timeslots = useMemo(() => timeslotsQuery.data ?? [], [timeslotsQuery.data])
  const draft = useAvailabilityDraft({ timeslots, rows: availabilityQuery.data, disabled: isSaving })

  if (!teacher) return null

  const handleSave = async () => {
    if (!draft.isDirty || isSaving) return
    setBlockMessage('')
    const attempt = attemptScope.capture()
    const payload = draft.buildPayload()
    try {
      await saveMutation.mutateAsync({ teacherId: teacher.id, payload, ...(onDate ? { onDate } : {}) })
      if (!attemptScope.isCurrent(attempt)) return
      draft.reset()
      toast.success('Disponibilidade guardada. Recomendações atualizadas.')
    } catch (error) {
      if (!attemptScope.isCurrent(attempt)) return
      const message = getApiErrorMessage(error, 'Não foi possível guardar a disponibilidade.')
      if (isApiErrorTransient(error)) toast.error(message)
      else setBlockMessage(message)
    }
  }

  const queryError = timeslotsQuery.error || availabilityQuery.error

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
        <CModalTitle>Disponibilidade — {teacher.name}</CModalTitle>
      </CModalHeader>
      <CModalBody>
        <p className="small text-muted">
          Esta edição é administrativa. Não envia convite nem altera o acesso do professor.
        </p>
        {blockMessage && <div className="mb-3"><FeedbackBanner tone="danger">{blockMessage}</FeedbackBanner></div>}
        {onDate && <p className="small">Grelha válida em {onDate.split('-').reverse().join('/')}.</p>}
        {timeslotsQuery.isLoading || availabilityQuery.isLoading ? (
          <StatePanel state="loading" title="A carregar disponibilidade" compact />
        ) : queryError ? (
          <StatePanel
            state="error"
            title="Não foi possível carregar a grelha"
            description="Verifique a ligação e tente novamente."
            compact
          />
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
        )}
      </CModalBody>
      <CModalFooter>
        <CButton color="secondary" variant="outline" onClick={onClose} disabled={isSaving}>
          Fechar
        </CButton>
        <CButton color="primary" onClick={() => { void handleSave() }} disabled={!draft.isDirty || isSaving}>
          {isSaving ? <><CSpinner size="sm" className="me-1" />A guardar…</> : 'Guardar disponibilidade'}
        </CButton>
      </CModalFooter>
    </CModal>
  )
}
