import { useMemo, useState } from 'react'
import {
  CAlert,
  CButton,
  CModal,
  CModalBody,
  CModalFooter,
  CModalHeader,
  CModalTitle,
  CSpinner,
} from '@coreui/react'
import AvailabilityGrid from './AvailabilityGrid'
import StatePanel from './StatePanel'
import { useTimeslots } from '../features/catalog/data'
import { useSaveTeacherAvailability, useTeacherAvailability } from '../features/operations/data'
import { DEFAULT_PREFERENCE, PREFERENCE_LEVELS } from '../constants'
import { getApiErrorMessage } from '../utils/apiErrors'

function toMap(rows = [], validIds) {
  return Object.fromEntries(
    rows
      .filter((row) => validIds.has(row.timeslot_id))
      .map((row) => [row.timeslot_id, Number(row.score)])
  )
}

/**
 * Direção edita a disponibilidade de um professor, incluindo quem não tem acesso.
 */
export default function TeacherAvailabilityModal({ teacher, onClose }) {
  const [draftEdits, setDraftEdits] = useState({})
  const [selectedScore, setSelectedScore] = useState(DEFAULT_PREFERENCE)
  const [feedback, setFeedback] = useState(null)
  const timeslotsQuery = useTimeslots()
  const availabilityQuery = useTeacherAvailability({ teacherId: teacher?.id })
  const saveMutation = useSaveTeacherAvailability()
  const timeslots = useMemo(() => timeslotsQuery.data ?? [], [timeslotsQuery.data])
  const validIds = useMemo(() => new Set(timeslots.map((slot) => slot.id)), [timeslots])
  const persistedMap = useMemo(
    () => toMap(Array.isArray(availabilityQuery.data) ? availabilityQuery.data : [], validIds),
    [availabilityQuery.data, validIds]
  )
  const draftMap = useMemo(() => ({ ...persistedMap, ...draftEdits }), [persistedMap, draftEdits])
  const changedIds = useMemo(
    () => Object.keys(draftEdits).filter(
      (id) => draftEdits[id] !== (persistedMap[id] ?? DEFAULT_PREFERENCE)
    ),
    [draftEdits, persistedMap]
  )
  const isDirty = changedIds.length > 0
  const isSaving = saveMutation.isPending

  if (!teacher) return null

  const handleGridChange = (id, score) => {
    if (isSaving) return
    setFeedback(null)
    setDraftEdits((current) => {
      const next = { ...current }
      if (score === (persistedMap[id] ?? DEFAULT_PREFERENCE)) delete next[id]
      else next[id] = score
      return next
    })
  }

  const handleSave = async () => {
    if (!isDirty || isSaving) return
    setFeedback(null)
    const payload = Object.entries(draftMap)
      .filter(([id]) => validIds.has(Number(id)))
      .map(([id, score]) => ({ timeslot_id: Number(id), score }))
    try {
      await saveMutation.mutateAsync({ teacherId: teacher.id, payload })
      setDraftEdits({})
      setFeedback({ tone: 'success', message: 'Disponibilidade guardada. Recomendações atualizadas.' })
    } catch (error) {
      setFeedback({
        tone: 'danger',
        message: getApiErrorMessage(error, 'Não foi possível guardar a disponibilidade.'),
      })
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
        {feedback && <CAlert color={feedback.tone}>{feedback.message}</CAlert>}
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
            <div className="availability-toolbar" role="toolbar" aria-label="Ferramentas de disponibilidade">
              <div className="availability-toolbar__tools">
                {[2, 1, 0, -1].map((score) => {
                  const info = PREFERENCE_LEVELS[score]
                  return (
                    <button
                      key={score}
                      type="button"
                      className={`availability-tool${selectedScore === score ? ' is-selected' : ''}`}
                      aria-pressed={selectedScore === score}
                      onClick={() => setSelectedScore(score)}
                      disabled={isSaving}
                    >
                      <span
                        className="availability-tool__swatch"
                        style={{ backgroundColor: info.color }}
                        aria-hidden="true"
                      />
                      {info.label}
                    </button>
                  )
                })}
              </div>
              <div className="availability-toolbar__status" aria-live="polite">
                {changedIds.length} {changedIds.length === 1 ? 'bloco alterado' : 'blocos alterados'}
              </div>
            </div>
            <AvailabilityGrid
              timeslots={timeslots}
              availabilityMap={draftMap}
              onChange={handleGridChange}
              selectedMode={selectedScore}
            />
          </>
        )}
      </CModalBody>
      <CModalFooter>
        <CButton color="secondary" variant="outline" onClick={onClose} disabled={isSaving}>
          Fechar
        </CButton>
        <CButton color="primary" onClick={() => { void handleSave() }} disabled={!isDirty || isSaving}>
          {isSaving ? <><CSpinner size="sm" className="me-1" />A guardar…</> : 'Guardar disponibilidade'}
        </CButton>
      </CModalFooter>
    </CModal>
  )
}
