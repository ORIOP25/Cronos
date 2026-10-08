import { render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import ContactDetailsStep from '../features/contact/components/ContactDetailsStep'

it('announces validation errors and focuses the first invalid contact field after submit', () => {
  const props = { answers: { name: '', email: '', phone: '' }, errors: {}, onChange: vi.fn(), onNext: vi.fn() }
  const { rerender } = render(<ContactDetailsStep {...props} />)
  screen.getByRole('button', { name: 'Continuar' }).focus()
  rerender(<ContactDetailsStep {...props} errors={{ name: 'Indique o seu nome.', email: 'Indique o seu email.' }} />)
  expect(screen.getByRole('textbox', { name: /^Nome/ })).toHaveFocus()
  expect(screen.getByRole('textbox', { name: /^Nome/ })).toHaveAccessibleDescription('Indique o seu nome.')
  expect(screen.getAllByRole('alert').map(element => element.textContent)).toEqual(['Indique o seu nome.', 'Indique o seu email.'])
  rerender(<ContactDetailsStep {...props} answers={{ ...props.answers, name: 'Ana', email: 'invalid' }} errors={{ email: 'Indique um email válido.' }} />)
  expect(screen.getByRole('textbox', { name: /^Email/ })).toHaveFocus()
  expect(screen.getByRole('textbox', { name: /^Email/ })).toHaveAccessibleDescription('Indique um email válido.')
  expect(screen.getByRole('alert')).toHaveTextContent('Indique um email válido.')
})
