import React, { useState, useEffect, useCallback } from 'react'
import PropTypes from 'prop-types'
import {
  CModal,
  CModalHeader,
  CModalTitle,
  CModalBody,
  CModalFooter,
  CButton,
  CFormTextarea,
  CAlert,
  CBadge,
  CSpinner,
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilCheckCircle, cilXCircle, cilActionUndo, cilWarning, cilPeople } from '@coreui/icons'
import { useUpsertLessonLog, useCreateOccurrence, useUpdateOccurrence } from '../hooks/useSchoolData'
import SubstitutionStep from './SubstitutionStep'

const STATUS_INFO = {
  COMPLETED: { label: 'Aula Dada', badge: 'success' },
  OCCURRENCE: { label: 'Falta Registada', badge: 'danger' },
  PENDING: { label: 'Pendente', badge: 'secondary' },
}

const OCCURRENCE_STATUS_LABELS = {
  GIVEN:       'Dada ✓',
  GAP:         'Furo ✗',
  SUBSTITUTED: 'Substituída ↔',
}

/**
 * LessonLogModal — unified lesson registration modal for both teachers and admins.
 *
 * Props:
 *   visible       — whether the modal is open
 *   onClose       — callback to close the modal
 *   slot          — the WeekSlot data object from the API
 *   isAdmin       — whether the current user is an admin (unlocks extra actions)
 */
const LessonLogModal = ({ visible, onClose, slot, isAdmin = false }) => {
  const [summary, setSummary] = useState('')
  const [notes, setNotes] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [step, setStep] = useState(1)
  const [occurrenceId, setOccurrenceId] = useState(null)
  const [substitutionError, setSubstitutionError] = useState('')

  const upsertLogMutation = useUpsertLessonLog()
  const createOccurrenceMutation = useCreateOccurrence()
  const updateOccurrenceMutation = useUpdateOccurrence()

  // Reset state when modal opens/closes
  useEffect(() => {
    if (visible && slot) {
      setSummary(slot.lesson_log_summary || '')
      setNotes(slot.lesson_log_notes || '')
      setErrorMessage('')
      setSubstitutionError('')
      setStep(1)
      setOccurrenceId(slot.occurrence_id || null)
    }
    if (!visible) {
      setStep(1)
      setOccurrenceId(null)
    }
  }, [visible, slot])

  const handleSubmit = async (status) => {
    setErrorMessage('')
    try {
      await upsertLogMutation.mutateAsync({
        scheduleOutputId: slot.schedule_output_id,
        payload: { status, summary, notes },
      })
      onClose()
    } catch (err) {
      const msg = err.response?.data?.detail || 'Erro ao guardar o registo. Tente novamente.'
      setErrorMessage(msg)
    }
  }

  const handleStartSubstitution = async () => {
    setErrorMessage('')
    setSubstitutionError('')

    // Edge-case: already has a decided occurrence
    if (slot.occurrence_id && slot.occurrence_decided_at) {
      setErrorMessage('Já existe uma ocorrência registada para este bloco. Consulte Faltas & Ocorrências para a gerir.')
      return
    }

    // Edge-case: timesheet closed
    if (slot.week_timesheet_status === 'SUBMITTED' || slot.week_timesheet_status === 'APPROVED') {
      setErrorMessage('A semana já foi submetida ou aprovada. Não é possível criar substituições.')
      return
    }

    // If occurrence already exists but not decided, reuse it
    if (slot.occurrence_id && !slot.occurrence_decided_at) {
      setOccurrenceId(slot.occurrence_id)
      setStep(2)
      return
    }

    // Create occurrence
    try {
      const occurrence = await createOccurrenceMutation.mutateAsync({
        scheduleOutputId: slot.schedule_output_id,
      })
      if (occurrence?.id) {
        setOccurrenceId(occurrence.id)
        setStep(2)
      } else {
        setErrorMessage('Não foi possível iniciar a substituição. Tente novamente.')
      }
    } catch (err) {
      const msg = err.response?.data?.detail || 'Erro ao criar ocorrência. Tente novamente.'
      setErrorMessage(msg)
    }
  }

  const handleConfirmSubstitution = useCallback(async ({ substituteTeacherId, substituteSubjectId }) => {
    setSubstitutionError('')
    try {
      await updateOccurrenceMutation.mutateAsync({
        id: occurrenceId,
        status: 'SUBSTITUTED',
        substituteTeacherId,
        substituteSubjectId,
      })
      onClose()
    } catch (err) {
      const msg = err.response?.data?.detail || 'Erro ao confirmar substituição. Tente novamente.'
      setSubstitutionError(msg)
    }
  }, [occurrenceId, updateOccurrenceMutation, onClose])

  const handleBackToStep1 = () => {
    setStep(1)
    setSubstitutionError('')
  }

  if (!slot) return null

  const currentStatus = slot.lesson_log_status || 'PENDING'
  const isCompleted = currentStatus === 'COMPLETED'
  const isOccurrence = currentStatus === 'OCCURRENCE'
  const isRegistered = isCompleted || isOccurrence

  // Occurrence data (LessonOccurrence — created via admin /absences flow)
  const hasOccurrence = Boolean(slot.occurrence_id)
  const occurrenceDecided = Boolean(slot.occurrence_decided_at)
  const occurrenceStatusLabel = OCCURRENCE_STATUS_LABELS[slot.occurrence_status] ?? slot.occurrence_status

  // Whether admin can show substitution button for this slot
  const canShowSubstitution = isAdmin && slot.is_past && slot.schedule_output_id && !occurrenceDecided

  // Calculate if the slot is truly in the future (combining date and end_time)
  let isFuture = false
  if (slot.date && slot.timeslot?.end_time) {
    const endDateTime = new Date(`${slot.date}T${slot.timeslot.end_time}`)
    isFuture = endDateTime > new Date()
  } else {
    isFuture = !slot.is_past
  }

  // Editing is locked when the timesheet is submitted/approved for the week
  const isLocked = isFuture || (slot.week_timesheet_status === 'SUBMITTED' || slot.week_timesheet_status === 'APPROVED')

  const statusInfo = STATUS_INFO[currentStatus] ?? STATUS_INFO.PENDING

  const formatDate = (dateStr) => {
    if (!dateStr) return '—'
    const d = new Date(`${dateStr}T12:00:00`)
    return d.toLocaleDateString('pt-PT', { day: '2-digit', month: 'long', year: 'numeric' })
  }

  return (
    <CModal visible={visible} onClose={onClose} alignment="center">
      <CModalHeader>
        <CModalTitle>
          {step === 1 ? 'Registo de Aula' : 'Substituição de Aula'}
          {' '}
          <CBadge
            color={statusInfo.badge}
            className="ms-2"
            style={{ fontSize: '0.7rem', verticalAlign: 'middle' }}
          >
            {statusInfo.label}
          </CBadge>
        </CModalTitle>
      </CModalHeader>

      <CModalBody>
        {/* Slot metadata */}
        <div
          className="mb-3 rounded px-3 py-2"
          style={{ backgroundColor: 'var(--color-bg-muted)', fontSize: '0.85rem' }}
        >
          <div><strong>Data:</strong> {formatDate(slot.date)}</div>
          <div><strong>Horário:</strong> {slot.timeslot ? `${slot.timeslot.start_time} – ${slot.timeslot.end_time}` : '—'}</div>
          <div><strong>Disciplina:</strong> {slot.subject?.name ?? '—'}</div>
          <div><strong>Turma:</strong> {slot.class_info?.name ?? '—'}</div>
          {isAdmin && <div><strong>Docente:</strong> {slot.teacher?.name ?? '—'}</div>}
          {slot.room && <div><strong>Sala:</strong> {slot.room?.name}</div>}
        </div>

        {/* Occurrence status banner (admin only — shows when there's an admin-created occurrence) */}
        {hasOccurrence && (
          <CAlert color={occurrenceDecided ? 'secondary' : 'warning'} className="mb-3 small py-2">
            <CIcon icon={cilWarning} className="me-1" />
            {occurrenceDecided
              ? `Ocorrência decidida: ${occurrenceStatusLabel}`
              : 'Ocorrência aberta — aguarda decisão em Faltas & Ocorrências.'}
          </CAlert>
        )}

        {errorMessage && (
          <CAlert color="danger" className="mb-3">
            {errorMessage}
          </CAlert>
        )}

        {isFuture && (
          <CAlert color="warning" className="mb-3">
            Esta aula ainda não terminou. O registo apenas estará disponível após a hora de término.
          </CAlert>
        )}

        {step === 2 ? (
          <SubstitutionStep
            occurrenceId={occurrenceId}
            onConfirm={handleConfirmSubstitution}
            onBack={handleBackToStep1}
            isLoading={updateOccurrenceMutation.isPending}
            errorMessage={substitutionError}
          />
        ) : (
          <>
            {/* Lesson log form */}
            <div className="mb-3">
              <label className="form-label fw-semibold">Sumário</label>
              <CFormTextarea
                rows={3}
                placeholder="Sumário descritivo da aula..."
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
                disabled={isLocked}
              />
            </div>
            <div className="mb-3">
              <label className="form-label fw-semibold">Notas Opcionais</label>
              <CFormTextarea
                rows={2}
                placeholder="Anotações para uso interno ou partilha com direção..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                disabled={isLocked}
              />
            </div>
          </>
        )}
      </CModalBody>

      {step === 1 && (
        <CModalFooter>
          {/* Left side: cancel + admin substitution action */}
          <div className="d-flex gap-2">
            <CButton color="secondary" variant="outline" onClick={onClose}>
              Cancelar
            </CButton>

            {/* Admin-only: start substitution wizard */}
            {canShowSubstitution && (
              <CButton
                color="warning"
                variant="outline"
                size="sm"
                onClick={handleStartSubstitution}
                disabled={createOccurrenceMutation.isPending || upsertLogMutation.isPending}
                title="Criar substituição para este bloco"
              >
                {createOccurrenceMutation.isPending ? (
                  <CSpinner size="sm" className="me-1" />
                ) : (
                  <CIcon icon={cilPeople} className="me-1" />
                )}
                Substituição
              </CButton>
            )}
          </div>

          {/* Right side: lesson log action buttons */}
          <div className="d-flex gap-2">
            {upsertLogMutation.isPending && <CSpinner size="sm" className="align-self-center" />}

            {isRegistered && (
              <CButton
                color="secondary"
                variant="outline"
                onClick={() => handleSubmit('PENDING')}
                disabled={upsertLogMutation.isPending || isLocked}
                title="Reverter para pendente"
              >
                <CIcon icon={cilActionUndo} className="me-1" />
                Reverter
              </CButton>
            )}

            {!isOccurrence && (
              <CButton
                style={{ backgroundColor: 'var(--color-state-gap)', borderColor: 'var(--color-state-gap)', color: '#fff' }}
                onClick={() => handleSubmit('OCCURRENCE')}
                disabled={isFuture || upsertLogMutation.isPending || isLocked}
                title="Registar que a aula não foi dada"
              >
                <CIcon icon={cilXCircle} className="me-1" />
                Registar Falta
              </CButton>
            )}

            {!isCompleted && (
              <CButton
                style={{ backgroundColor: 'var(--color-state-given)', borderColor: 'var(--color-state-given)', color: '#fff' }}
                onClick={() => handleSubmit('COMPLETED')}
                disabled={isFuture || upsertLogMutation.isPending || isLocked}
                title="Marcar aula como dada"
              >
                <CIcon icon={cilCheckCircle} className="me-1" />
                Aula Dada
              </CButton>
            )}
          </div>
        </CModalFooter>
      )}
    </CModal>
  )
}

LessonLogModal.propTypes = {
  visible: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  slot: PropTypes.object,
  isAdmin: PropTypes.bool,
}

export default LessonLogModal
