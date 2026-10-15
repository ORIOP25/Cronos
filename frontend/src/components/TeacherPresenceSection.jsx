/* eslint-disable react-refresh/only-export-components -- pure rule helpers live with the section */
import { CButton, CFormCheck, CFormFeedback, CFormInput } from '@coreui/react'
import FeedbackBanner from './FeedbackBanner'

const EMPTY_PRESENCE_DRAFT = { lunch_required: true, minimum_hours: '', max_gap_hours: '' }

const PRESENCE_MIN_HOURS_MESSAGE = 'O mínimo tem de estar entre 1 e 12 horas.'
const PRESENCE_GAP_HOURS_MESSAGE = 'O furo máximo tem de estar entre 0 e 12 horas.'
const PRESENCE_PAIR_MESSAGE = 'Indique o mínimo e o furo máximo, ou deixe os dois vazios.'

const asHours = (value) => (value === '' || value == null ? '' : Number(value))
const isEmptyHours = (value) => value === '' || value == null

export function presenceDraftFromServer(presence) {
  return {
    lunch_required: presence?.lunch_required ?? true,
    minimum_hours: asHours(presence?.minimum_hours),
    max_gap_hours: asHours(presence?.max_gap_hours),
  }
}

export function presencePayloadFromDraft(draft) {
  return {
    lunch_required: Boolean(draft.lunch_required),
    minimum_hours: isEmptyHours(draft.minimum_hours) ? null : Number(draft.minimum_hours),
    max_gap_hours: isEmptyHours(draft.max_gap_hours) ? null : Number(draft.max_gap_hours),
  }
}

export function arePresenceDraftsEqual(first, second) {
  return first.lunch_required === second.lunch_required
    && first.minimum_hours === second.minimum_hours
    && first.max_gap_hours === second.max_gap_hours
}

/**
 * The API envelope hides field detail, so the client owns the exact Portuguese
 * messages (D05). A minimum and a gap are both empty or both set.
 */
export function validatePresenceDraft(draft) {
  const errors = {}
  const minEmpty = isEmptyHours(draft.minimum_hours)
  const gapEmpty = isEmptyHours(draft.max_gap_hours)

  if (!minEmpty && (!Number.isInteger(draft.minimum_hours) || draft.minimum_hours < 1 || draft.minimum_hours > 12)) {
    errors.minimum_hours = PRESENCE_MIN_HOURS_MESSAGE
  }
  if (!gapEmpty && (!Number.isInteger(draft.max_gap_hours) || draft.max_gap_hours < 0 || draft.max_gap_hours > 12)) {
    errors.max_gap_hours = PRESENCE_GAP_HOURS_MESSAGE
  }
  if (minEmpty !== gapEmpty) {
    errors.max_gap_hours = PRESENCE_PAIR_MESSAGE
  }
  return errors
}

/**
 * D05: the gap only lives with a minimum. Setting a minimum for the first time
 * leaves the gap at 1; clearing the minimum clears the gap.
 */
function changeMinimumHours(draft, rawValue) {
  const minimumHours = rawValue === '' ? '' : Number(rawValue)
  if (minimumHours === '') {
    return { ...draft, minimum_hours: '', max_gap_hours: '' }
  }
  if (isEmptyHours(draft.max_gap_hours)) {
    return { ...draft, minimum_hours: minimumHours, max_gap_hours: 1 }
  }
  return { ...draft, minimum_hours: minimumHours }
}

function changeMaximumGap(draft, rawValue) {
  return { ...draft, max_gap_hours: rawValue === '' ? '' : Number(rawValue) }
}

/**
 * "Presença na escola" secção do modal de disponibilidade (D11). The controls
 * stay disabled while the saved rule loads or the read fails, so a default
 * value never overwrites the stored rule (T08, R24).
 */
export default function TeacherPresenceSection({
  draft,
  fieldErrors = {},
  onChange,
  disabled,
  isLoading,
  isError,
  onRetry,
}) {
  const value = draft ?? EMPTY_PRESENCE_DRAFT
  const hasMinimum = !isEmptyHours(value.minimum_hours)

  return (
    <section className="border rounded p-3" aria-labelledby="teacher-presence-title">
      <h5 id="teacher-presence-title" className="h6 fw-bold mb-2">Presença na escola</h5>
      <p className="small text-muted mb-3">Vale para todas as grelhas e anos letivos.</p>

      {isLoading && <p className="small text-muted mb-3" role="status">A carregar a regra de presença…</p>}
      {isError && (
        <div className="mb-3">
          <FeedbackBanner
            tone="warning"
            action={onRetry ? <CButton color="link" className="p-0" onClick={onRetry}>Tentar novamente</CButton> : undefined}
          >
            Não foi possível carregar a regra de presença.
          </FeedbackBanner>
        </div>
      )}

      <fieldset disabled={Boolean(disabled)} className="border-0 p-0 m-0">
        <legend className="fs-6 fw-semibold mb-2">Tem de ter hora de almoço?</legend>
        <div className="d-flex gap-3 mb-3">
          <CFormCheck
            type="radio"
            name="teacher-presence-lunch"
            id="teacher-presence-lunch-yes"
            label="Sim"
            checked={value.lunch_required === true}
            onChange={() => onChange({ ...value, lunch_required: true })}
          />
          <CFormCheck
            type="radio"
            name="teacher-presence-lunch"
            id="teacher-presence-lunch-no"
            label="Não"
            checked={value.lunch_required === false}
            onChange={() => onChange({ ...value, lunch_required: false })}
          />
        </div>

        <div className="mb-3" style={{ maxWidth: '400px' }}>
          <CFormInput
            type="number"
            id="teacher-presence-minimum-hours"
            label="Mínimo de horas por presença"
            min={1}
            max={12}
            value={value.minimum_hours}
            invalid={Boolean(fieldErrors.minimum_hours)}
            aria-describedby={['teacher-presence-minimum-hours-help', fieldErrors.minimum_hours && 'teacher-presence-minimum-hours-feedback'].filter(Boolean).join(' ')}
            onChange={(event) => onChange(changeMinimumHours(value, event.target.value))}
          />
          <small id="teacher-presence-minimum-hours-help" className="text-muted d-block mt-1">
            Vazio = sem mínimo. Uma presença é a manhã ou a tarde, separadas pelo almoço. Sem hora de almoço, o dia inteiro conta como uma presença.
          </small>
          {fieldErrors.minimum_hours && (
            <CFormFeedback id="teacher-presence-minimum-hours-feedback" className="d-block" invalid>
              {fieldErrors.minimum_hours}
            </CFormFeedback>
          )}
        </div>

        {hasMinimum && (
          <div className="mb-2" style={{ maxWidth: '400px' }}>
            <CFormInput
              type="number"
              id="teacher-presence-maximum-gap"
              label="Furo máximo dentro da presença"
              min={0}
              max={12}
              value={value.max_gap_hours}
              invalid={Boolean(fieldErrors.max_gap_hours)}
              aria-describedby={fieldErrors.max_gap_hours ? 'teacher-presence-maximum-gap-feedback' : undefined}
              onChange={(event) => onChange(changeMaximumGap(value, event.target.value))}
            />
            {fieldErrors.max_gap_hours && (
              <CFormFeedback id="teacher-presence-maximum-gap-feedback" className="d-block" invalid>
                {fieldErrors.max_gap_hours}
              </CFormFeedback>
            )}
          </div>
        )}
      </fieldset>
    </section>
  )
}
