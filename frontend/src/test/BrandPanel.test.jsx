import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import BrandPanel from '../components/auth/BrandPanel'

describe('BrandPanel', () => {
  it('uses the white logo treatment on dark authentication surfaces', () => {
    render(<BrandPanel tagline="Planeamento escolar" stats={[]} />)

    expect(screen.getByRole('img', { name: /cronos/i })).toHaveClass('zen-auth-logo')
  })
})
