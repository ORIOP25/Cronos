import { CFormLabel, CFormCheck } from '@coreui/react'

const DAYS = [
  { value: 0, label: 'Segunda-feira' },
  { value: 1, label: 'Terça-feira' },
  { value: 2, label: 'Quarta-feira' },
  { value: 3, label: 'Quinta-feira' },
  { value: 4, label: 'Sexta-feira' },
  { value: 5, label: 'Sábado' },
]

export function DaysStep({ values, fieldErrors, onChange }) {
  const selectedDays = values.days_of_week || [0, 1, 2, 3, 4]

  const toggleDay = (dayVal) => {
    const next = selectedDays.includes(dayVal)
      ? selectedDays.filter((d) => d !== dayVal)
      : [...selectedDays, dayVal].sort((a, b) => a - b)
    onChange('days_of_week', next)
  }

  return (
    <div className="foundation-step-days">
      <h4 className="h5 mb-3 text-dark fw-bold">2. Dias de Funcionamento Letivo</h4>
      <p className="text-muted small mb-4">
        Selecione os dias da semana em que a sua instituição tem atividades letivas regulares.
      </p>

      <div className="mb-4">
        <CFormLabel className="fw-semibold">Dias Letivos Semanais *</CFormLabel>
        <div className="d-flex flex-wrap gap-3 mt-2">
          {DAYS.map((d) => (
            <CFormCheck
              key={d.value}
              id={`day-${d.value}`}
              label={d.label}
              checked={selectedDays.includes(d.value)}
              onChange={() => toggleDay(d.value)}
            />
          ))}
        </div>
        {fieldErrors.days_of_week && (
          <div className="text-danger small mt-2">{fieldErrors.days_of_week}</div>
        )}
      </div>
    </div>
  )
}
