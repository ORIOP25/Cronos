import { cleanup, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { publicIdentity } from '../features/marketing/content/publicIdentity'
import LegalDocumentLayout from '../features/legal/LegalDocumentLayout'
import { renderWithRouter } from './testUtils'

afterEach(() => cleanup())

describe('privacy legal document', () => {
  it('publishes a substantial responsible-party trust anchor', () => {
    renderWithRouter(<LegalDocumentLayout kind="privacy" />, { initialEntries: ['/privacidade'] })
    const text = document.body.textContent.replace(/\s+/g, ' ').trim()
    expect(text.length).toBeGreaterThan(500)
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
    expect(screen.getByRole('heading', { name: 'Política de Privacidade' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: publicIdentity.email })).toHaveAttribute('href', `mailto:${publicIdentity.email}`)
    expect(screen.getByText(new RegExp(publicIdentity.address.street))).toBeInTheDocument()
    const headingLevels = [...document.querySelectorAll('h1, h2, h3, h4, h5, h6')].map((heading) => Number(heading.tagName.slice(1)))
    expect(headingLevels.every((level, index) => index === 0 || level - headingLevels[index - 1] <= 1)).toBe(true)
  })
})
