import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import FeedbackBanner from '../components/FeedbackBanner'

describe('FeedbackBanner', () => {
  it('announces errors immediately with a decorative icon', () => {
    const { container } = render(<FeedbackBanner tone="danger">Não foi possível guardar.</FeedbackBanner>)

    expect(screen.getByRole('alert')).toHaveTextContent('Não foi possível guardar.')
    const icon = container.querySelector('.feedback-banner__icon')
    expect(icon).not.toBeNull()
    expect(icon).toHaveAttribute('aria-hidden', 'true')
  })

  it('announces other tones politely', () => {
    render(<FeedbackBanner tone="warning">As aulas afetadas mudaram.</FeedbackBanner>)
    expect(screen.getByRole('status')).toHaveTextContent('As aulas afetadas mudaram.')
  })

  it('keeps a title and an adjacent action inside the content', () => {
    render(
      <FeedbackBanner tone="info" title="Fluxo guardado" action={<button type="button">Regenerar horário</button>}>
        Três aulas saíram do horário ativo.
      </FeedbackBanner>,
    )

    expect(screen.getByText('Fluxo guardado')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Regenerar horário' })).toBeInTheDocument()
  })
})
