import { CCard, CCardBody, CBadge } from '@coreui/react'
import { buildDailyTimeslots } from '../foundationModel'

const DAY_LABELS = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']

export function PreviewStep({ values, fieldErrors }) {
  const slots = buildDailyTimeslots(values)
  const days = (values.days_of_week || [0, 1, 2, 3, 4]).map((d) => DAY_LABELS[d] || `Dia ${d}`)

  return (
    <div className="foundation-step-preview">
      <h4 tabIndex="-1" className="h5 mb-3 text-dark fw-bold">7. Pré-visualização da Grelha Horária</h4>
      <p className="text-muted small mb-4">
        Com base nos horários, durações e intervalos configurados, o Cronos gerará a seguinte estrutura diária de tempos letivos.
      </p>

      {fieldErrors.preview && (
        <div className="alert alert-danger mb-4" role="alert">
          {fieldErrors.preview}
        </div>
      )}

      <div className="d-flex flex-wrap gap-2 mb-3">
        <span className="text-muted small align-self-center">Dias ativos:</span>
        {days.map((day) => (
          <CBadge key={day} color="primary" className="p-2">
            {day}
          </CBadge>
        ))}
      </div>

      <CCard className="border-0 shadow-sm bg-light mb-4">
        <CCardBody>
          <h6 className="fw-bold text-secondary mb-3">
            Estrutura Diária Calculada ({slots.length} tempos letivos por dia)
          </h6>
          {slots.length === 0 ? (
            <p className="text-muted small mb-0">Nenhum tempo letivo gerado. Verifique os horários e durações.</p>
          ) : (
            <div className="d-flex flex-column gap-2">
              {slots.map((slot) => (
                <div
                  key={slot.id}
                  className="d-flex justify-content-between align-items-center p-2 bg-white rounded border border-light"
                >
                  <span className="fw-semibold text-dark">
                    {slot.index}.º Tempo Letivo
                  </span>
                  <span className="font-monospace text-primary fw-medium">
                    {slot.start} — {slot.end}
                  </span>
                </div>
              ))}
            </div>
          )}
        </CCardBody>
      </CCard>
    </div>
  )
}
