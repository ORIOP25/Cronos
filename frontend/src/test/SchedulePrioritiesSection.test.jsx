import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SchoolConfig from '../pages/SchoolConfig'
import { renderWithProviders } from './testUtils'

vi.mock('../apiClient', () => ({
  default: {
    get: vi.fn(),
    put: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    defaults: { withCredentials: true },
  },
  setClerkTokenGetter: vi.fn(),
}))

import apiClient from '../apiClient'

const DEFAULTS = {
  finish_early: 4,
  teacher_gaps: 3,
  class_gaps: 2,
  teacher_single_lessons: 2,
  class_single_lessons: 2,
  teacher_preferences: 3,
  class_preferences: 2,
  class_same_room: 2,
  weekly_stability: 2,
  subject_pace: 3,
  update_stability: 3,
}

const CRITERIA = [
  'Acabar os módulos o mais cedo possível.',
  'Evitar tempos livres dos professores.',
  'Evitar tempos livres das turmas.',
  'Evitar que um professor venha à escola para uma só aula.',
  'Evitar que uma turma venha à escola para uma só aula.',
  'Respeitar Evitar e Preferencial dos professores.',
  'Respeitar Evitar e Preferencial das turmas.',
  'Manter a turma na mesma sala.',
  'Manter o horário igual de semana para semana.',
  'Avançar as disciplinas ao mesmo ritmo.',
  'Nas atualizações, mexer pouco no horário publicado.',
]

const PRIORITIES_RESPONSE = { levels: DEFAULTS, defaults: DEFAULTS }

describe('Schedule priorities configuration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiClient.get.mockImplementation((url) => {
      if (url === '/school/settings/') {
        return Promise.resolve({
          school_start_date: '2026-09-15',
          school_hard_end_date: '2027-07-31',
          repair_stability_window_days: 14,
        })
      }
      if (url === '/school/settings/schedule-priorities') {
        return Promise.resolve(PRIORITIES_RESPONSE)
      }
      return Promise.resolve([])
    })
    apiClient.put.mockImplementation((_url, payload) => Promise.resolve({
      levels: payload.levels,
      defaults: DEFAULTS,
    }))
  })

  it('shows each criterion with five accessible levels and the exact guidance', async () => {
    renderWithProviders(<SchoolConfig />)
    fireEvent.click(screen.getByRole('tab', { name: 'Prioridades do horário' }))

    expect(await screen.findByText(
      'Escolha a importância de cada critério. O Cronos equilibra-os segundo estes valores. As regras obrigatórias (Impossível, presença mínima, almoço, tipo de sala e datas do ano letivo) nunca se quebram.',
    )).toBeInTheDocument()

    for (const criterion of CRITERIA) {
      const fieldset = screen.getByText(criterion).closest('fieldset')
      expect(fieldset).not.toBeNull()
      expect(within(fieldset).getAllByRole('radio')).toHaveLength(5)
    }
    expect(screen.getAllByRole('radio')).toHaveLength(55)
    expect(screen.getByText(/O professor pode ficar com horas vazias entre aulas/)).toBeInTheDocument()
    expect(screen.getByText(/O Cronos só usa um bloco Evitar quando o horário não caberia de outra forma/)).toBeInTheDocument()
    expect(screen.getByText('Nível recomendado: Prioridade máxima')).toBeInTheDocument()
  })

  it('saves the selected level and resets the draft from server defaults without saving', async () => {
    renderWithProviders(<SchoolConfig />)
    fireEvent.click(screen.getByRole('tab', { name: 'Prioridades do horário' }))

    const classGaps = await screen.findByText(CRITERIA[2])
    const fieldset = classGaps.closest('fieldset')
    const veryImportant = within(fieldset).getByRole('radio', { name: 'Muito importante' })
    fireEvent.click(veryImportant)
    expect(veryImportant).toHaveAttribute('aria-checked', 'true')

    fireEvent.click(screen.getByRole('button', { name: 'Guardar prioridades' }))
    await waitFor(() => expect(apiClient.put).toHaveBeenCalledWith(
      '/school/settings/schedule-priorities',
      { levels: { ...DEFAULTS, class_gaps: 3 } },
    ))
    expect(await screen.findByText(
      'Prioridades guardadas. A próxima geração ou atualização usa estes valores.',
    )).toBeInTheDocument()

    fireEvent.click(within(fieldset).getByRole('radio', { name: 'Importante' }))
    fireEvent.click(screen.getByRole('button', { name: 'Repor valores recomendados' }))
    expect(within(fieldset).getByRole('radio', { name: 'Importante' })).toHaveAttribute(
      'aria-checked',
      'true',
    )
    expect(apiClient.put).toHaveBeenCalledTimes(1)
  })
})
