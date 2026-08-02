import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import ProcessStepperSection from '../components/marketing/ProcessStepperSection'
import GeneratorSection from '../components/marketing/GeneratorSection'
import RoutineSection from '../components/marketing/RoutineSection'
import ShinyText from '../components/marketing/ShinyText'
const shinyTextStyles = readFileSync(resolve('src/components/marketing/ShinyText.css'), 'utf8')

describe('marketing interactive sections', () => {
  it('moves through the process stepper and keeps navigation boundaries disabled', () => {
    render(<ProcessStepperSection />)

    expect(screen.getByRole('heading', { name: 'Preparar escola' })).toBeInTheDocument()
    const previousButton = screen.getByRole('button', { name: /Anterior/ })
    const nextButton = screen.getByRole('button', { name: /Seguinte/ })
    expect(previousButton).toBeDisabled()
    expect(nextButton).not.toBeDisabled()

    fireEvent.click(nextButton)
    expect(screen.getByRole('heading', { name: 'Recolher disponibilidades' })).toBeInTheDocument()
    expect(previousButton).not.toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: /Ver Etapa 06/ }))
    expect(screen.getByRole('heading', { name: 'Acompanhar progresso' })).toBeInTheDocument()
    expect(nextButton).toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: /Ver Etapa 01/ }))
    expect(screen.getByRole('heading', { name: 'Preparar escola' })).toBeInTheDocument()
    expect(previousButton).toBeDisabled()
  })

  it('switches the generator list between inputs and outputs', () => {
    render(<GeneratorSection />)

    const inputsTab = screen.getByRole('button', { name: /O Cronos recebe/ })
    const outputsTab = screen.getByRole('button', { name: /A escola recebe/ })
    expect(inputsTab).toHaveClass('is-active')
    expect(screen.getByText('Cursos profissionais, turmas e anos de ciclo')).toBeInTheDocument()

    fireEvent.click(outputsTab)
    expect(outputsTab).toHaveClass('is-active')
    expect(screen.getByText(/Horários harmoniosos e prontos a usar/)).toBeInTheDocument()
    expect(screen.queryByText('Cursos profissionais, turmas e anos de ciclo')).not.toBeInTheDocument()

    fireEvent.click(inputsTab)
    expect(inputsTab).toHaveClass('is-active')
    expect(screen.getByText('Cursos profissionais, turmas e anos de ciclo')).toBeInTheDocument()
  })

  it('updates the routine story and checklist when a chapter changes', () => {
    render(<RoutineSection />)

    const firstChapter = screen.getByRole('button', { name: /Antes da semana começar/ })
    expect(firstChapter).toHaveClass('is-active')
    expect(screen.getByRole('heading', { name: 'A escola prepara o terreno' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Quando o horário é publicado/ }))
    expect(screen.getByRole('heading', { name: 'Cada pessoa vê o que tem pela frente' })).toBeInTheDocument()
    expect(screen.getByText('Horário semanal por turma.')).toBeInTheDocument()
    expect(firstChapter).not.toHaveClass('is-active')
  })


  it('uses CSS animation props and exposes reduced-motion safeguards for ShinyText', () => {
    const { rerender } = render(
      <ShinyText text="Cronos" direction="right" yoyo pauseOnHover speed={2} delay={1} />,
    )
    const shinyText = screen.getByText('Cronos')

    expect(shinyText).toHaveClass('shiny-text', 'shiny-text--pause-on-hover')
    expect(shinyText.style.getPropertyValue('--shiny-animation-direction')).toBe('alternate-reverse')
    expect(shinyText.style.getPropertyValue('--shiny-speed')).toBe('2s')
    expect(shinyText.style.getPropertyValue('--shiny-delay')).toBe('1s')

    rerender(<ShinyText text="Cronos" disabled />)
    expect(screen.getByText('Cronos')).toHaveClass('shiny-text--disabled')
    expect(screen.getByText('Cronos').getAttribute('style')).toBe('')
    expect(shinyTextStyles).toMatch(/prefers-reduced-motion: reduce/)
    expect(shinyTextStyles).toMatch(/animation:\s*none/)
    expect(shinyTextStyles).toMatch(/background-position:\s*50% center/)
  })
})
