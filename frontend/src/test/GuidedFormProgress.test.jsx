import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import GuidedFormProgress from '../components/GuidedFormProgress'

describe('GuidedFormProgress', () => {
  it('starts empty, advances evenly, and ends full', () => {
    const { rerender } = render(<GuidedFormProgress current={1} total={5} />)
    const progress = screen.getByRole('progressbar')

    expect(progress.style.getPropertyValue('--guided-form-progress')).toBe('0%')

    rerender(<GuidedFormProgress current={3} total={5} />)
    expect(progress.style.getPropertyValue('--guided-form-progress')).toBe('50%')

    rerender(<GuidedFormProgress current={5} total={5} />)
    expect(progress.style.getPropertyValue('--guided-form-progress')).toBe('100%')
  })
})
