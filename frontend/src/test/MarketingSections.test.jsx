import { describe, expect, it } from 'vitest'
import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { renderWithRouter } from './testUtils'
import HomePage from '../pages/marketing/HomePage'
import VantagensPage from '../pages/marketing/VantagensPage'
import HowItWorksPage from '../pages/marketing/HowItWorksPage'
import AboutPage from '../pages/marketing/AboutPage'
import WorkflowTabs from '../features/marketing/components/workflow/WorkflowTabs'
import FaqSection from '../features/marketing/components/help/FaqSection'
import MarketingHeader from '../features/marketing/components/layout/MarketingHeader'

describe('public marketing sections', () => {
  it('renders the homepage sections in the approved narrative order', () => {
    renderWithRouter(<HomePage />)
    const headings = screen.getAllByRole('heading').map((heading) => heading.textContent)
    expect(headings.indexOf('Gestão de Horários para o Ensino Profissional')).toBeLessThan(headings.indexOf('Uma falta hoje não pode estragar o planeamento de junho'))
    expect(headings).toContain('Resolva uma substituição em menos de 1 minuto')
    expect(headings).toContain('O horário muda sem apagar o que já aconteceu')
    expect(headings).toContain('Feito para quem mantém a escola a funcionar')
    expect(screen.getAllByRole('link', { name: 'Pedir demonstração' }).every((link) => link.getAttribute('href') === '/contacto')).toBe(true)
  })

  it('keeps public headings free of final periods', () => {
    const pages = [
      <HomePage key="home" />,
      <VantagensPage key="advantages" />,
      <HowItWorksPage key="workflow" />,
      <AboutPage key="about" />,
      <FaqSection key="help" />,
    ]
    pages.forEach((page) => {
      renderWithRouter(page)
      screen.getAllByRole('heading').forEach((heading) => expect(heading.textContent.trim()).not.toMatch(/\.$/))
      cleanup()
    })
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
    fireEvent.click(firstStep)
    expect(firstStep).toHaveAttribute('aria-pressed', 'true')
    expect(document.querySelector('.cronos-minute-visual')).toHaveStyle({ '--active-step': '0' })
  })

  it('keeps the homepage hero image free of duplicated overlays and notes', () => {
    renderWithRouter(<HomePage />)
    expect(document.querySelector('.cronos-hero__schedule')).not.toBeInTheDocument()
    expect(screen.queryByText('Uma visão operacional para cada decisão.')).not.toBeInTheDocument()
    expect(screen.getAllByRole('img')).toHaveLength(4)
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
})
