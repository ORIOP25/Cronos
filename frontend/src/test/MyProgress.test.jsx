import { fireEvent, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MyProgress from '../pages/MyProgress'
import { renderWithRouter } from './testUtils'

const { progress } = vi.hoisted(() => ({ progress: vi.fn() }))

vi.mock('../features/members/data', () => ({
  useCurrentMember: () => ({ data: { teacher_id: 7 } }),
}))
vi.mock('../features/operations/data', () => ({
  useTeacherProgress: () => progress(),
}))

describe('MyProgress compact class overview', () => {
  beforeEach(() => {
    progress.mockReturnValue({ data: [{ class_id: 1, class_name: '10.º A', course_name: 'Informática', grade_level: 10,
      subjects: [{ subject_id: 11, subject_name: 'Programação', completed_hours: 20, total_hours: 40, overall_percentage: 50 },
        { subject_id: 12, subject_name: 'Português', completed_hours: 30, total_hours: 40, overall_percentage: 75 }],
    }], isLoading: false, isError: false })
  })

  it('starts with a class summary and reveals every discipline on request', () => {
    renderWithRouter(<MyProgress />)
    const title = screen.getByText('10.º A')
    const disclosure = title.closest('details')
    expect(disclosure).not.toBeNull()
    expect(disclosure).not.toHaveAttribute('open')
    expect(within(disclosure).getByText('Média: 63%')).toBeVisible()
    expect(within(disclosure).getByText('Programação')).not.toBeVisible()
    fireEvent.click(title.closest('summary'))
    expect(disclosure).toHaveAttribute('open')
    expect(within(disclosure).getByText('Programação')).toBeVisible()
    expect(within(disclosure).getByText('Português')).toBeVisible()
    expect(within(disclosure).getByText('20h / 40h')).toBeVisible()
    fireEvent.click(title.closest('summary'))
    expect(disclosure).not.toHaveAttribute('open')
  })

  it('makes the native class disclosure reachable by keyboard', async () => {
    renderWithRouter(<MyProgress />)
    await userEvent.tab()
    expect(screen.getByText('10.º A').closest('summary')).toHaveFocus()
  })
})
