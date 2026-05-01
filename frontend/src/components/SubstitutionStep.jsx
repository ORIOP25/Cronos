import React, { useEffect, useMemo, useState } from 'react'
import PropTypes from 'prop-types'
import {
  CButton,
  CFormSelect,
  CFormLabel,
  CAlert,
  CSpinner,
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilWarning, cilCheckCircle, cilArrowLeft } from '@coreui/icons'
import { useSubstituteRecommendations } from '../hooks/useSchoolData'

/**
 * SubstitutionStep — Passo 2 do wizard de registo de aula.
 *
 * Permite ao admin escolher um professor substituto a partir das recomendações
 * do backend e confirmar a substituição.
 */
const SubstitutionStep = ({
  occurrenceId,
  onConfirm,
  onBack,
  isLoading,
  errorMessage,
}) => {
  const {
    data: recommendations = [],
    isLoading: loadingRecommendations,
    isError: recommendationsError,
  } = useSubstituteRecommendations({ occurrenceId })

  const defaultRecommendation = useMemo(() => {
    if (recommendations.length === 0) return ''
    const first = recommendations[0]
    return `${first.teacher_id}:${first.subject_id}`
  }, [recommendations])

  const [overrideRecommendation, setOverrideRecommendation] = useState(null)
  const selectedRecommendation = overrideRecommendation ?? defaultRecommendation

  const orderedRecommendations = useMemo(
    () => [...recommendations].sort((a, b) => a.rank - b.rank || a.teacher_id - b.teacher_id),
    [recommendations]
  )

  const selectedRecommendationData = orderedRecommendations.find(
    (rec) => `${rec.teacher_id}:${rec.subject_id}` === selectedRecommendation
  )

  const handleConfirm = () => {
    if (!selectedRecommendationData) return
    onConfirm({
      substituteTeacherId: selectedRecommendationData.teacher_id,
      substituteSubjectId: selectedRecommendationData.subject_id,
    })
  }

  return (
    <div>
      <div className="d-flex align-items-center gap-2 mb-3">
        <CButton color="secondary" variant="outline" size="sm" onClick={onBack}>
          <CIcon icon={cilArrowLeft} className="me-1" />
          Voltar ao Registo
        </CButton>
      </div>

      <CAlert color="info" className="mb-3">
        <CIcon icon={cilWarning} className="me-1" />
        Selecione o professor substituto e a disciplina a lecionar.
      </CAlert>

      {errorMessage && (
        <CAlert color="danger" className="mb-3">
          {errorMessage}
        </CAlert>
      )}

      <div className="mb-3">
        <CFormLabel htmlFor="substituteRecommendation">
          Candidato recomendado
        </CFormLabel>

        {loadingRecommendations && (
          <div className="d-flex align-items-center gap-2 text-muted small">
            <CSpinner size="sm" />
            <span>A carregar recomendações…</span>
          </div>
        )}

        {!loadingRecommendations && recommendationsError && (
          <CAlert color="danger" className="mb-0">
            Não foi possível carregar as recomendações de professores substitutos. Tente novamente.
          </CAlert>
        )}

        {!loadingRecommendations && !recommendationsError && recommendations.length === 0 && (
          <CAlert color="warning" className="mb-0">
            Sem elegíveis para este slot. Registe como falta ou volte atrás.
          </CAlert>
        )}

        {!loadingRecommendations && !recommendationsError && recommendations.length > 0 && (
          <>
            <CFormSelect
              id="substituteRecommendation"
                    value={selectedRecommendation}
                    onChange={(e) => setOverrideRecommendation(e.target.value)}
            >
              <option value="">— Selecionar candidato —</option>
              {orderedRecommendations.map((rec) => (
                <option
                  key={`${rec.teacher_id}-${rec.subject_id}`}
                  value={`${rec.teacher_id}:${rec.subject_id}`}
                >
                  #{rec.rank} {rec.teacher_name} — {rec.subject_name}
                </option>
              ))}
            </CFormSelect>

            {selectedRecommendationData && (
              <div
                className="mt-2 rounded px-3 py-2"
                style={{ backgroundColor: 'var(--color-bg-muted)', fontSize: '0.85rem' }}
              >
                <div><strong>Justificação:</strong> {selectedRecommendationData.justification}</div>
                <div className="text-muted">
                  Substituições no período: {selectedRecommendationData.substitutions_in_period} ·
                  Carga diária: {selectedRecommendationData.daily_load_hours}h
                </div>
              </div>
            )}
          </>
        )}
      </div>

      <div className="d-flex justify-content-end gap-2">
        <CButton color="secondary" variant="outline" onClick={onBack}>
          Voltar
        </CButton>
        <CButton
          color="warning"
          onClick={handleConfirm}
          disabled={
            isLoading ||
            loadingRecommendations ||
            !selectedRecommendationData ||
            recommendationsError
          }
        >
          {isLoading ? (
            <>
              <CSpinner size="sm" className="me-1" />
              A confirmar…
            </>
          ) : (
            <>
              <CIcon icon={cilCheckCircle} className="me-1" />
              Confirmar Substituição
            </>
          )}
        </CButton>
      </div>
    </div>
  )
}

SubstitutionStep.propTypes = {
  occurrenceId: PropTypes.number.isRequired,
  onConfirm: PropTypes.func.isRequired,
  onBack: PropTypes.func.isRequired,
  isLoading: PropTypes.bool,
  errorMessage: PropTypes.string,
}

SubstitutionStep.defaultProps = {
  isLoading: false,
  errorMessage: '',
}

export default SubstitutionStep
