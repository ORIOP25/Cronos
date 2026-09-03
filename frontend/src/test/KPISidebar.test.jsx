import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import KPISidebar from '../components/schedules/KPISidebar'

describe('KPISidebar', () => {
  it('renders loading spinner and message when isLoading is true', () => {
    render(<KPISidebar subjects={[]} isLoading={true} />)

    expect(screen.getByTestId('kpi-loading')).toBeInTheDocument()
    expect(screen.getByText('A carregar progresso...')).toBeInTheDocument()
  })

  it('renders error message when isError is true', () => {
    render(<KPISidebar subjects={[]} isError={true} />)

    expect(screen.getByTestId('kpi-error')).toBeInTheDocument()
    expect(screen.getByText('Erro ao carregar o progresso da turma.')).toBeInTheDocument()
  })

  it('renders empty state when subjects list is empty and not loading or error', () => {
    render(<KPISidebar subjects={[]} />)

    expect(screen.getByText('Nenhuma disciplina com progresso disponível.')).toBeInTheDocument()
  })

  it('renders subjects with fractional hours and percentage correctly', () => {
    const mockSubjects = [
      {
        id: 1,
        name: 'Tecnologias Web',
        total_hours: 25.0,
        completed_hours: 0.8,
        overall_percentage: 3.3,
      },
    ]

    render(<KPISidebar subjects={mockSubjects} />)

    expect(screen.getByText('Tecnologias Web')).toBeInTheDocument()
    expect(screen.getByText('0.8h / 25h')).toBeInTheDocument()
    expect(screen.getByText('3.3%')).toBeInTheDocument()

    const progressBar = screen.getByRole('progressbar', { name: /tecnologias web: 3\.3%/i })
    expect(progressBar).toBeInTheDocument()
    expect(progressBar).toHaveAttribute('value', '3.3')
    expect(progressBar).toHaveAttribute('max', '100')
  })
})
