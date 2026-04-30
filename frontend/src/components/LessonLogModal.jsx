import React, { useState, useEffect } from 'react'
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
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilCheckCircle, cilXCircle, cilActionUndo } from '@coreui/icons'
import { useUpsertLessonLog } from '../hooks/useSchoolData'

const STATUS_INFO = {
  COMPLETED: { label: 'Aula Dada', badge: 'success' },
  OCCURRENCE: { label: 'Falta Registada', badge: 'danger' },
  PENDING: { label: 'Pendente', badge: 'secondary' },
}

const LessonLogModal = ({ visible, onClose, slot }) => {
  const [summary, setSummary] = useState('')
  const [notes, setNotes] = useState('')
  const [errorMessage, setErrorMessage] = useState('')

  const upsertLogMutation = useUpsertLessonLog()

  useEffect(() => {
    if (visible && slot) {
      setSummary(slot.lesson_log_summary || '')
      setNotes(slot.lesson_log_notes || '')
      setErrorMessage('')
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

  if (!slot) return null

  const currentStatus = slot.lesson_log_status || 'PENDING'
  const isCompleted = currentStatus === 'COMPLETED'
  const isOccurrence = currentStatus === 'OCCURRENCE'
  const isRegistered = isCompleted || isOccurrence

  // Calculate if the slot is truly in the future (combining date and end_time)
  let isFuture = false
  if (slot.date && slot.timeslot?.end_time) {
    const endDateTime = new Date(`${slot.date}T${slot.timeslot.end_time}`)
    isFuture = endDateTime > new Date()
  } else {
    isFuture = !slot.is_past
  }

  const statusInfo = STATUS_INFO[currentStatus] ?? STATUS_INFO.PENDING

  return (
    <CModal visible={visible} onClose={onClose} alignment="center">
      <CModalHeader>
        <CModalTitle>
          Registo de Aula
          {' '}
          <CBadge color={statusInfo.badge} className="ms-2" style={{ fontSize: '0.7rem', verticalAlign: 'middle' }}>
            {statusInfo.label}
          </CBadge>
        </CModalTitle>
      </CModalHeader>
      <CModalBody>
        <div className="mb-3 text-muted small">
          <strong>Data:</strong> {slot.date} <br />
          <strong>Disciplina:</strong> {slot.subject?.name} <br />
          <strong>Turma:</strong> {slot.class_info?.name} <br />
        </div>

        {errorMessage && (
          <CAlert color="danger" className="mb-3">
            {errorMessage}
          </CAlert>
        )}

        {isFuture && (
          <CAlert color="warning" className="mb-3">
            Esta aula ainda não terminou ou está no futuro. O registo apenas estará disponível após a hora de término.
          </CAlert>
        )}

        <div className="mb-3">
          <label className="form-label fw-semibold">Sumário</label>
          <CFormTextarea
            rows={3}
            placeholder="Sumário descritivo da aula..."
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            disabled={isFuture}
          />
        </div>
        <div className="mb-3">
          <label className="form-label fw-semibold">Notas Opcionais</label>
          <CFormTextarea
            rows={2}
            placeholder="Anotações para uso interno ou partilha com direção..."
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            disabled={isFuture}
          />
        </div>
      </CModalBody>
      <CModalFooter className="d-flex justify-content-between">
        <CButton color="secondary" variant="outline" onClick={onClose}>
          Cancelar
        </CButton>

        <div className="d-flex gap-2">
          {isRegistered && (
            <CButton
              color="secondary"
              variant="outline"
              onClick={() => handleSubmit('PENDING')}
              disabled={upsertLogMutation.isPending}
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
              disabled={isFuture || upsertLogMutation.isPending}
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
              disabled={isFuture || upsertLogMutation.isPending}
              title="Marcar aula como dada"
            >
              <CIcon icon={cilCheckCircle} className="me-1" />
              Aula Dada
            </CButton>
          )}
        </div>
      </CModalFooter>
    </CModal>
  )
}

LessonLogModal.propTypes = {
  visible: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  slot: PropTypes.object,
}

export default LessonLogModal
