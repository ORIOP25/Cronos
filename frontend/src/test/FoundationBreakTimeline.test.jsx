import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { BreakDurationStep } from '../features/foundation/components/BreakDurationStep'
import { initialFoundationDraftValues } from '../features/foundation/foundationModel'

const variableValues = {
  ...initialFoundationDraftValues,
  opening_time: '09:00',
  closing_time: '12:10',
  slot_duration_minutes: 50,
  break_duration_minutes: 10,
  break_overrides: [{ after_slot: 2, duration_minutes: 5 }],
}

function Harness({ values: initialValues, fieldErrors = {} }) {
  const [values, setValues] = useState(initialValues)
  return (
    <BreakDurationStep
      values={values}
      fieldErrors={fieldErrors}
      onChange={(field, value) => setValues((current) => ({ ...current, [field]: value }))}
    />
  )
}

describe('BreakDurationStep variable pauses', () => {
  it('names each gap control after its lesson and shows the next lesson start', () => {
    render(<Harness values={variableValues} />)

    expect(screen.getByLabelText('Pausa após a aula 1 (09:00-09:50)')).toHaveValue(10)
    expect(screen.getByLabelText('Pausa após a aula 2 (10:00-10:50)')).toHaveValue(5)
    expect(screen.queryByLabelText(/Pausa após a aula 3/)).not.toBeInTheDocument()

    expect(screen.getByText('Segue-se a aula 2 às 10:00')).toBeInTheDocument()
    expect(screen.getByText('Segue-se a aula 3 às 10:55')).toBeInTheDocument()
  })

  it('turns a changed gap into an override and recomputes the timeline', () => {
    render(<Harness values={{ ...variableValues, break_overrides: [] }} />)

    fireEvent.change(screen.getByLabelText('Pausa após a aula 1 (09:00-09:50)'), {
      target: { value: '0' },
    })

    expect(screen.getByLabelText('Pausa após a aula 2 (09:50-10:40)')).toHaveValue(10)
    expect(screen.getByText('Segue-se a aula 3 às 10:50')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Repor padrão após a aula 1' })).toBeInTheDocument()
  })

  it('restores the usual pause when the override is reset', () => {
    render(<Harness values={variableValues} />)

    expect(screen.getByText('Segue-se a aula 3 às 10:55')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Repor padrão após a aula 2' }))

    expect(screen.getByText('Segue-se a aula 3 às 11:00')).toBeInTheDocument()
    expect(screen.getByLabelText('Pausa após a aula 2 (10:00-10:50)')).toHaveValue(10)
    expect(screen.queryByRole('button', { name: /Repor padrão/ })).not.toBeInTheDocument()
  })

  it('shows the validation error for an override without a following lesson', () => {
    render(
      <Harness
        values={{
          ...initialFoundationDraftValues,
          opening_time: '09:00',
          closing_time: '09:50',
          break_duration_minutes: 10,
          break_overrides: [{ after_slot: 2, duration_minutes: 5 }],
        }}
      />,
    )

    expect(screen.getByRole('alert')).toHaveTextContent('aula 2')
  })

  it('keeps the timeline usable and reports an invalid override duration', () => {
    render(
      <Harness
        values={{
          ...variableValues,
          break_overrides: [{ after_slot: 1, duration_minutes: -50 }],
        }}
      />,
    )

    expect(screen.getByLabelText('Pausa após a aula 1 (09:00-09:50)')).toHaveValue(10)
    expect(screen.getByRole('alert')).toHaveTextContent('0 e 60')
    expect(screen.getByText('Segue-se a aula 2 às 10:00')).toBeInTheDocument()
  })

  it('lets the administrator remove an override that lost its following lesson', () => {
    render(
      <Harness
        values={{
          ...initialFoundationDraftValues,
          opening_time: '09:00',
          closing_time: '09:50',
          break_duration_minutes: 10,
          break_overrides: [{ after_slot: 2, duration_minutes: 5 }],
        }}
      />,
    )

    expect(screen.getByRole('alert')).toHaveTextContent('aula 2')
    fireEvent.click(screen.getByRole('button', { name: 'Remover ajuste após a aula 2' }))

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByText(/sem aula seguinte/)).not.toBeInTheDocument()
  })
})
