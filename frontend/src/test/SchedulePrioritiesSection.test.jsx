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

const WARNINGS = {
  'Evitar tempos livres dos professores.': 'Atenção: Em Prioridade máxima, muitos mais professores podem vir à escola para uma só aula.',
  'Respeitar Evitar e Preferencial dos professores.': 'Atenção: Numa escola com o horário muito cheio, Muito importante e Prioridade máxima podem dar o mesmo horário.',
  'Manter o horário igual de semana para semana.': 'Atenção: Em Prioridade máxima, os tempos livres dos professores podem duplicar, os das turmas aumentam, e o ano acaba mais tarde.',
  'Avançar as disciplinas ao mesmo ritmo.': 'Atenção: Em Ignorar, o horário tende a piorar noutros critérios: mais tempos livres e mais blocos Evitar dos professores, e o ano acaba mais tarde.',
}

const INTRO =
  'Escolha a importância de cada critério. O Cronos equilibra-os segundo estes valores. As regras obrigatórias (Impossível, presença mínima, almoço, tipo de sala e datas do ano letivo) nunca se quebram. O Cronos acaba sempre os módulos o mais cedo possível, para deixar margem para recuperar faltas e ocorrências. Os critérios abaixo decidem como, e alguns podem atrasar o fim do ano.'

const CRITERIA = [
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

    expect(await screen.findByText(INTRO)).toBeInTheDocument()

    expect(screen.queryByText('Acabar os módulos o mais cedo possível.')).not.toBeInTheDocument()
    expect(screen.getAllByRole('radiogroup')).toHaveLength(10)
    for (const criterion of CRITERIA) {
      const fieldset = screen.getByText(criterion).closest('fieldset')
      expect(fieldset).not.toBeNull()
      expect(within(fieldset).getAllByRole('radio')).toHaveLength(5)
    }
    expect(screen.getAllByRole('radio')).toHaveLength(50)
    expect(screen.getByText(/O professor pode ficar com muitas horas vazias entre aulas/)).toBeInTheDocument()
    expect(screen.getByText(/O Cronos só usa um bloco Evitar quando o horário não caberia de outra forma/)).toBeInTheDocument()
    expect(screen.getAllByText(/^Nível recomendado: /)).toHaveLength(10)
    expect(within(screen.getByText(CRITERIA[0]).closest('fieldset')).getByText('Nível recomendado: Muito importante'))
      .toBeInTheDocument()
    // Criteria 4 and 5 count whole days with a single lesson (owner, 21 Oct 2026).
    expect(screen.getByText(/^Dias em que o professor tem uma única aula/)).toBeInTheDocument()
    expect(screen.getByText(/^Dias em que a turma tem uma única aula/)).toBeInTheDocument()
    expect(screen.queryByText(/Turnos \(manhã ou tarde\)/)).not.toBeInTheDocument()
  })

  it('shows the warnings as discreet secondary text after the impact lines, only where they exist', async () => {
    renderWithProviders(<SchoolConfig />)
    fireEvent.click(screen.getByRole('tab', { name: 'Prioridades do horário' }))

    await screen.findByText(CRITERIA[0])
    expect(screen.getAllByText(/^Atenção: /)).toHaveLength(Object.keys(WARNINGS).length)
    for (const criterion of CRITERIA) {
      const fieldset = screen.getByText(criterion).closest('fieldset')
      const warningText = WARNINGS[criterion]
      if (!warningText) {
        expect(within(fieldset).queryByText(/^Atenção: /)).not.toBeInTheDocument()
        continue
      }
      const warning = within(fieldset).getByText(warningText)
      const highest = within(fieldset).getByText(/^Prioridade máxima:/)
      const recommended = within(fieldset).getByText(/^Nível recomendado:/)
      expect(warning.tagName).toBe('P')
      expect(warning).toHaveClass('small', 'text-body-secondary')
      expect(warning.closest('.alert')).toBeNull()
      expect(highest.compareDocumentPosition(warning) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
      expect(warning.compareDocumentPosition(recommended) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    }
  })

  it('saves the selected level and resets the draft from server defaults without saving', async () => {
    renderWithProviders(<SchoolConfig />)
    fireEvent.click(screen.getByRole('tab', { name: 'Prioridades do horário' }))

    const classGaps = await screen.findByText('Evitar tempos livres das turmas.')
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

  it('keeps the submitted draft locked until its save finishes', async () => {
    const finishRequests = []
    apiClient.put.mockImplementation((_url, payload) => new Promise((resolve) => {
      finishRequests.push(() => resolve({ levels: payload.levels, defaults: DEFAULTS }))
    }))

    renderWithProviders(<SchoolConfig />)
    fireEvent.click(screen.getByRole('tab', { name: 'Prioridades do horário' }))

    const fieldset = (await screen.findByText('Evitar tempos livres das turmas.')).closest('fieldset')
    const veryImportant = within(fieldset).getByRole('radio', { name: 'Muito importante' })
    fireEvent.click(within(fieldset).getByText('Muito importante', { exact: true }))
    fireEvent.click(screen.getByRole('button', { name: 'Guardar prioridades' }))
    await waitFor(() => expect(apiClient.put).toHaveBeenCalledTimes(1))

    try {
      fireEvent.click(within(fieldset).getByText('Prioridade máxima', { exact: true }))
      fireEvent.click(screen.getByRole('button', { name: 'Repor valores recomendados' }))
      fireEvent.click(screen.getByRole('button', { name: 'Guardar prioridades' }))

      expect(apiClient.put).toHaveBeenCalledTimes(1)
      expect(veryImportant).toBeChecked()
      expect(screen.getByRole('button', { name: 'Repor valores recomendados' })).toBeDisabled()
    } finally {
      for (const finishRequest of finishRequests) finishRequest()
    }

    expect(await screen.findByText(
      'Prioridades guardadas. A próxima geração ou atualização usa estes valores.',
    )).toBeInTheDocument()
    fireEvent.click(within(fieldset).getByText('Prioridade máxima', { exact: true }))
    expect(within(fieldset).getByRole('radio', { name: 'Prioridade máxima' })).toBeChecked()
  })
})
