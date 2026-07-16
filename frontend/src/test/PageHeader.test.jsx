import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import PageHeader from '../components/PageHeader'

describe('PageHeader', () => {
  it('renders node titles and header actions', () => {
    render(
      <PageHeader
        preTitle="Configuração"
        title={<><span>Horários</span> <em>Beta</em></>}
      >
        <button type="button">Criar horário</button>
      </PageHeader>,
    )

    expect(screen.getByRole('heading', { name: 'Horários Beta' })).toBeInTheDocument()
    expect(screen.getByText('Configuração')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Criar horário' })).toBeInTheDocument()
  })
})
