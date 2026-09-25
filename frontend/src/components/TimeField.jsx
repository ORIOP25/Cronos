import { CFormFeedback, CFormInput, CFormLabel, CInputGroup, CInputGroupText } from '@coreui/react'
import { formatTimeOfDay } from '../utils/timeOfDay'

export function TimeField({ id, label, value, error, onChange }) {
  const unitId = `${id}-unit`
  const feedbackId = `${id}-feedback`
  return (
    <>
      {label && <CFormLabel htmlFor={id}>{label}</CFormLabel>}
      <CInputGroup>
        <CFormInput
          type="text"
          inputMode="numeric"
          id={id}
          name={id}
          value={formatTimeOfDay(value)}
          invalid={Boolean(error)}
          aria-describedby={error ? `${unitId} ${feedbackId}` : unitId}
          onChange={(event) => onChange(event.target.value)}
        />
        <CInputGroupText id={unitId}>h</CInputGroupText>
      </CInputGroup>
      {error && (
        <CFormFeedback id={feedbackId} invalid className="d-block">
          {error}
        </CFormFeedback>
      )}
    </>
  )
}
