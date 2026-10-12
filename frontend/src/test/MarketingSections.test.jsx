import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { renderWithRouter } from './testUtils'
import { resetClerkState, setClerkState } from './setup'
import HomePage from '../pages/marketing/HomePage'
import VantagensPage from '../pages/marketing/VantagensPage'
import WorkflowTabs from '../features/marketing/components/workflow/WorkflowTabs'
import TeacherWorkflowSection from '../features/marketing/components/workflow/TeacherWorkflowSection'
import FaqSection from '../features/marketing/components/help/FaqSection'
import MarketingHeader from '../features/marketing/components/layout/MarketingHeader'
import MarketingLayout from '../features/marketing/components/layout/MarketingLayout'

vi.mock('../features/marketing/hooks/useMarketingMetadata', () => ({
  useMarketingMetadata: vi.fn(),
}))

describe('public marketing sections', () => {
  beforeEach(() => resetClerkState())

  it('renders the homepage sections in the approved narrative order', () => {
    renderWithRouter(<HomePage />)
    const headings = screen.getAllByRole('heading').map((heading) => heading.textContent)
    expect(headings.indexOf('Gestão de Horários para o Ensino Profissional')).toBeLessThan(headings.indexOf('Uma falta hoje não pode estragar o planeamento de junho'))
    expect(headings).toContain('Resolva uma substituição em menos de 1 minuto')
    expect(headings).toContain('O horário muda sem apagar o que já aconteceu')
    expect(headings).toContain('Feito para quem mantém a escola a funcionar')
    expect(headings.indexOf('Feito para quem mantém a escola a funcionar')).toBeLessThan(headings.indexOf('O horário mudou. O professor soube?'))
    expect(headings.indexOf('O horário mudou. O professor soube?')).toBeLessThan(headings.indexOf('O dia do professor começa no horário'))
    expect(screen.getByRole('region', { name: 'Horário e rotina do professor' })).toBeInTheDocument()
    expect(screen.getByText('Defina preferências')).toBeInTheDocument()
    expect(screen.getByText('Consulte alterações')).toBeInTheDocument()
    expect(screen.getByText('Registe a aula')).toBeInTheDocument()
    expect(screen.getByText('Acompanhe UFCDs')).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'Pedir demonstração' }).every((link) => link.getAttribute('href') === '/contacto')).toBe(true)
  })

  it('adds the teacher perspective without changing the advantages page structure', () => {
    renderWithRouter(<VantagensPage />)
    expect(screen.getByText('Professores sem saber qual é a versão certa')).toBeInTheDocument()
    expect(screen.getByText(/alterações dispersas por mensagens e ficheiros/i)).toBeInTheDocument()
    expect(screen.getByText('Para os Professores')).toBeInTheDocument()
  })

  it('supports keyboard selection in workflow tabs', () => {
    renderWithRouter(<WorkflowTabs />)
    const tabs = screen.getAllByRole('tab')
    fireEvent.keyDown(tabs[0], { key: 'ArrowRight' })
    expect(tabs[1]).toHaveAttribute('aria-selected', 'true')
    expect(document.querySelector('.cronos-workflow-visual--adapt')).toBeInTheDocument()
    fireEvent.keyDown(tabs[1], { key: 'End' })
    expect(tabs[2]).toHaveAttribute('aria-selected', 'true')
    expect(document.querySelector('.cronos-workflow-visual--finish')).toBeInTheDocument()
  })

  it('explains the teacher workflow with simple accessible tabs', () => {
    renderWithRouter(<TeacherWorkflowSection />)
    const tabs = screen.getAllByRole('tab', { name: /preparar|lecionar|acompanhar/i })
    expect(tabs).toHaveLength(3)
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true')
    fireEvent.keyDown(tabs[0], { key: 'ArrowRight' })
    expect(tabs[1]).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('heading', { name: 'A aula começa no bloco certo' })).toBeInTheDocument()
    expect(screen.getByText('A coordenação decide faltas e substituições.')).toBeInTheDocument()
  })

  it('reveals one minute-workflow step at a time', () => {
    renderWithRouter(<HomePage />)
    const secondStep = screen.getByRole('button', { name: /passo 2: escolher um substituto elegível/i })
    const firstStep = screen.getByRole('button', { name: /passo 1: registar a falta/i })
    const thirdStep = screen.getByRole('button', { name: /passo 3: confirmar a decisão/i })
    fireEvent.click(secondStep)
    expect(secondStep).toHaveAttribute('aria-pressed', 'true')
    expect(document.querySelector('.cronos-minute-visual')).toHaveStyle({ '--active-step': '1' })
    fireEvent.click(thirdStep)
    expect(thirdStep).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('00:59')).toBeInTheDocument()
    fireEvent.click(firstStep)
    expect(firstStep).toHaveAttribute('aria-pressed', 'true')
    expect(document.querySelector('.cronos-minute-visual')).toHaveStyle({ '--active-step': '0' })
  })

  it('starts the FAQ closed and keeps one answer open', () => {
    renderWithRouter(<FaqSection />)
    const questions = screen.getAllByRole('button')
    expect(questions[0]).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(questions[0])
    expect(questions[0]).toHaveAttribute('aria-expanded', 'true')
    expect(document.querySelector('#faq-panel-professional')).toHaveAttribute('aria-hidden', 'false')
    fireEvent.click(questions[1])
    expect(questions[0]).toHaveAttribute('aria-expanded', 'false')
    expect(document.querySelector('#faq-panel-professional')).toHaveAttribute('aria-hidden', 'true')
    expect(questions[1]).toHaveAttribute('aria-expanded', 'true')
  })

  it('does not focus the mobile menu button on load and restores focus only after Escape', async () => {
    renderWithRouter(<MarketingHeader />)
    const toggle = screen.getByRole('button', { name: 'Abrir menu de navegação' })
    expect(document.activeElement).not.toBe(toggle)
    fireEvent.click(toggle)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await waitFor(() => expect(document.activeElement).toBe(toggle))
  })

  it('routes pending sessions to Clerk tasks without rendering marketing content', () => {
    setClerkState({ sessionStatus: 'pending', currentTask: { key: 'choose-organization' } })
    renderWithRouter(
      <Routes>
        <Route element={<MarketingLayout />}>
          <Route path="/" element={<div data-testid="marketing-content">Marketing</div>} />
        </Route>
      </Routes>,
    )

    expect(screen.queryByTestId('marketing-content')).not.toBeInTheDocument()
    expect(screen.getByTestId('redirect-to-tasks')).toBeInTheDocument()
    expect(screen.queryByTestId('redirect-to-sign-in')).not.toBeInTheDocument()
  })
})
