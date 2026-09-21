import { useRef } from 'react'
import { CFormInput } from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilCalendar } from '@coreui/icons'
import { formatDateInput, parseDateInput } from '../utils/formatUtils'

export default function PortugueseDateInput({ value = '', onChange, min, max, disabled, readOnly, ...props }) {
  const calendarRef = useRef(null)

  const openCalendar = () => {
    if (disabled || readOnly) return
    if (calendarRef.current?.showPicker) {
      calendarRef.current.showPicker()
    } else {
      calendarRef.current?.click()
    }
  }

  const handleChange = (event) => {
    const nextValue = event.target.value
    const parsedValue = parseDateInput(nextValue)
    if (parsedValue !== null) onChange(parsedValue)
  }

  const handleBlur = (event) => {
    const parsedValue = parseDateInput(event.target.value)
    if (parsedValue === null) {
      event.target.value = ''
      onChange('')
      return
    }
    event.target.value = formatDateInput(parsedValue)
    if (parsedValue !== value) onChange(parsedValue)
  }

  return (
    <div className="portuguese-date-input">
      <CFormInput
        {...props}
        key={value || 'empty-date'}
        type="text"
        inputMode="numeric"
        autoComplete="off"
        placeholder="dd/mm/aaaa"
        defaultValue={formatDateInput(value)}
        disabled={disabled}
        readOnly={readOnly}
        onChange={handleChange}
        onBlur={handleBlur}
        onClick={openCalendar}
      />
      <button
        type="button"
        className="portuguese-date-input__button"
        aria-label="Abrir calendário"
        title="Abrir calendário"
        disabled={disabled || readOnly}
        onClick={openCalendar}
      >
        <CIcon icon={cilCalendar} aria-hidden="true" />
      </button>
      <input
        ref={calendarRef}
        className="portuguese-date-input__calendar"
        type="date"
        value={value}
        min={min}
        max={max}
        tabIndex={-1}
        aria-hidden="true"
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  )
}
