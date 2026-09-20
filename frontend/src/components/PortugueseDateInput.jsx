import { CFormInput } from '@coreui/react'
import { formatDateInput, parseDateInput } from '../utils/formatUtils'

export default function PortugueseDateInput({ value = '', onChange, ...props }) {
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
    <CFormInput
      {...props}
      key={value || 'empty-date'}
      type="text"
      inputMode="numeric"
      autoComplete="off"
      placeholder="dd/mm/aaaa"
      defaultValue={formatDateInput(value)}
      onChange={handleChange}
      onBlur={handleBlur}
    />
  )
}
