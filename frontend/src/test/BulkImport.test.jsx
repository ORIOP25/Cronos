import { act, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import BulkImport from '../pages/BulkImport'
import { renderWithRouter } from './testUtils'
import { resetClerkState, setClerkState } from './setup'

const mocks = vi.hoisted(() => ({
  validate: vi.fn(),
  commit: vi.fn(),
  download: vi.fn(),
}))

vi.mock('../ApiClientContext', () => ({
  useApiClient: () => ({}),
}))

vi.mock('../features/imports/data', async () => {
  const actual = await vi.importActual('../features/imports/data')
  return {
    ...actual,
    downloadBulkImportTemplate: mocks.download,
    useValidateBulkImport: () => ({ mutateAsync: mocks.validate, isPending: false, isError: false }),
    useCommitBulkImport: () => ({ mutateAsync: mocks.commit, isPending: false, isError: false }),
  }
})

describe('BulkImport', () => {
  afterEach(resetClerkState)
  beforeEach(() => {
    mocks.validate.mockReset()
    mocks.commit.mockReset()
    mocks.download.mockReset()
    mocks.download.mockResolvedValue(undefined)
    mocks.validate.mockResolvedValue({
      can_commit: true,
      preview: { counts: { rooms: 1 }, items: [] },
      issues: [],
    })
    mocks.commit.mockResolvedValue({ created_counts: { rooms: 1 }, warnings: [] })
  })

  function renderPage() {
    return renderWithRouter(<BulkImport />, { initialEntries: ['/imports'], withToaster: true })
  }

  function downloadButtonForCard(label) {
    return within(screen.getByText(label).parentElement).getByRole('button', { name: 'Descarregar modelo' })
  }

  function cardFor(label) {
    return screen.getByText(label).closest('.import-resource')
  }

  it('keeps file inputs visible and resource guidance collapsed until requested', async () => {
    renderPage()
    const row = cardFor('Salas')
    const guidance = within(row).getByText('Como preencher').closest('details')
    expect(guidance).not.toHaveAttribute('open')
    expect(within(row).getByLabelText('Selecionar ficheiro CSV de salas')).toBeVisible()
    await userEvent.click(within(row).getByText('Como preencher'))
    expect(guidance).toHaveAttribute('open')
  })

  it('presents plain-language instructions without technical implementation terms', () => {
    renderPage()

    expect(screen.getByRole('heading', { name: 'Importar dados' })).toBeInTheDocument()
    expect(
      screen.getByText(
        'Descarregue um modelo, preencha e escolha os ficheiros a importar.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByText('Descarregue o modelo da secção pretendida.')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Descarregar modelo' })).toHaveLength(8)
    expect(screen.queryByText(/UTF-8|BOM|backend|atómica|Recurso|JSON/i)).not.toBeInTheDocument()
  })

  it('describes room types by the school-defined name instead of a fixed list', () => {
    renderPage()

    expect(
      screen.getAllByText('Tipo de sala: escreva o nome do tipo. Um nome que a escola ainda não tem cria um tipo novo.'),
    ).toHaveLength(2)
    expect(screen.queryByText(/Laboratório, Ginásio ou Artes/)).not.toBeInTheDocument()
  })

  it('lists the room types the import will create, once, with the count', async () => {
    const user = userEvent.setup()
    mocks.validate.mockResolvedValueOnce({
      can_commit: true,
      preview: {
        counts: { rooms: 1, subjects: 1, room_types: 1 },
        items: [{ resource: 'room_types', name: 'oficina' }],
      },
      issues: [],
    })
    renderPage()

    const file = new File(['x'], 'Cronos_Salas_Template.csv', { type: 'text/csv' })

    await user.upload(screen.getByLabelText('Selecionar ficheiro CSV de salas'), file)
    await user.click(screen.getByRole('button', { name: 'Verificar ficheiros' }))

    expect(await screen.findByText('Tipos de sala novos: 1')).toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'Tipos de sala novos' })).toHaveTextContent('oficina')
  })

  it('lists the class availability section with its instructions', () => {
    renderPage()

    expect(screen.getByText('Disponibilidade das turmas')).toBeInTheDocument()
    expect(
      screen.getByText('Cada linha é uma turma num dia. Cada coluna de hora é um bloco.'),
    ).toBeInTheDocument()
    expect(
      within(cardFor('Disponibilidade das turmas')).getByText(
        'Não apague colunas de hora. Se a grelha mudar, descarregue um modelo novo.',
      ),
    ).toBeInTheDocument()
    expect(
      screen.getByLabelText('Selecionar ficheiro CSV de disponibilidade das turmas'),
    ).toBeInTheDocument()
  })

  it('lists the teacher availability section with its instructions', () => {
    renderPage()

    expect(screen.getByText('Disponibilidade dos professores')).toBeInTheDocument()
    expect(
      screen.getByText(
        'O email identifica o professor. O nome serve só para ler o ficheiro.',
      ),
    ).toBeInTheDocument()
    expect(
      screen.getByLabelText('Selecionar ficheiro CSV de disponibilidade dos professores'),
    ).toBeInTheDocument()
  })

  it('lists the teacher presence section with its instructions', () => {
    renderPage()

    expect(screen.getByText('Presença dos professores')).toBeInTheDocument()
    expect(
      screen.getByText('Hora de almoço: Sim ou Não. Uma célula vazia vale Sim.'),
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        'Cada linha substitui os três valores desse professor. Os professores ausentes ficam iguais.',
      ),
    ).toBeInTheDocument()
    expect(
      screen.getByLabelText('Selecionar ficheiro CSV de presença dos professores'),
    ).toBeInTheDocument()
  })

  it('lists the class availability preview rows with course, class and changed blocks', async () => {
    const user = userEvent.setup()
    mocks.validate.mockResolvedValueOnce({
      can_commit: true,
      preview: {
        counts: { class_availability: 2 },
        items: [
          { resource: 'rooms', name: 'Sala 1', line: 2 },
          {
            resource: 'class_availability',
            course_abbreviation: 'TGEI',
            class_name: 'TGEI 25/28',
            changed_blocks: 3,
            line: 2,
          },
          {
            resource: 'class_availability',
            course_abbreviation: 'TM',
            class_name: 'TM 24/27',
            changed_blocks: 0,
            line: 4,
          },
        ],
      },
      issues: [],
    })
    renderPage()
    const file = new File(['x'], 'Cronos_DisponibilidadeTurmas_Template.csv', { type: 'text/csv' })

    await user.upload(
      screen.getByLabelText('Selecionar ficheiro CSV de disponibilidade das turmas'),
      file,
    )
    await user.click(screen.getByRole('button', { name: 'Verificar ficheiros' }))

    const table = await screen.findByRole('table', {
      name: 'Disponibilidade das turmas por turma',
    })
    expect(within(table).getByRole('columnheader', { name: 'Sigla do curso' })).toBeInTheDocument()
    expect(within(table).getByRole('columnheader', { name: 'Nome da turma' })).toBeInTheDocument()
    expect(
      within(table).getByRole('columnheader', { name: 'Blocos que mudam' }),
    ).toBeInTheDocument()
    expect(within(table).getAllByRole('row')).toHaveLength(3)
    expect(within(table).getByText('TGEI')).toBeInTheDocument()
    expect(within(table).getByText('TGEI 25/28')).toBeInTheDocument()
    expect(within(table).getByText('3')).toBeInTheDocument()
    expect(within(table).getByText('TM 24/27')).toBeInTheDocument()
    expect(within(table).getByText('Sem alterações')).toBeInTheDocument()
    expect(within(table).queryByText('0')).not.toBeInTheDocument()
    expect(within(table).queryByText('Sala 1')).not.toBeInTheDocument()
    expect(screen.getByText('Disponibilidade das turmas: 2')).toBeInTheDocument()
  })

  it('lists the teacher availability preview rows with name, email and changed blocks', async () => {
    const user = userEvent.setup()
    mocks.validate.mockResolvedValueOnce({
      can_commit: true,
      preview: {
        counts: { teacher_availability: 2 },
        items: [
          {
            resource: 'teacher_availability',
            teacher_name: 'Ana Silva',
            teacher_email: 'ana.silva@escola.pt',
            changed_blocks: 4,
            line: 2,
          },
          {
            resource: 'teacher_availability',
            teacher_name: 'Bruno Costa',
            teacher_email: 'bruno.costa@escola.pt',
            changed_blocks: 0,
            line: 6,
          },
        ],
      },
      issues: [],
    })
    renderPage()
    const file = new File(['x'], 'Cronos_DisponibilidadeProfessores_Template.csv', { type: 'text/csv' })

    await user.upload(
      screen.getByLabelText('Selecionar ficheiro CSV de disponibilidade dos professores'),
      file,
    )
    await user.click(screen.getByRole('button', { name: 'Verificar ficheiros' }))

    const table = await screen.findByRole('table', {
      name: 'Disponibilidade dos professores por professor',
    })
    expect(within(table).getByRole('columnheader', { name: 'Nome do professor' })).toBeInTheDocument()
    expect(within(table).getByRole('columnheader', { name: 'Email do professor' })).toBeInTheDocument()
    expect(
      within(table).getByRole('columnheader', { name: 'Blocos que mudam' }),
    ).toBeInTheDocument()
    expect(within(table).getByText('Ana Silva')).toBeInTheDocument()
    expect(within(table).getByText('ana.silva@escola.pt')).toBeInTheDocument()
    expect(within(table).getByText('4')).toBeInTheDocument()
    expect(within(table).getByText('bruno.costa@escola.pt')).toBeInTheDocument()
    expect(within(table).getByText('Sem alterações')).toBeInTheDocument()
    expect(screen.getByText('Disponibilidade dos professores: 2')).toBeInTheDocument()
  })

  it('shows both availability tables together with Blocos que mudam and Sem alterações', async () => {
    const user = userEvent.setup()
    mocks.validate.mockResolvedValueOnce({
      can_commit: true,
      preview: {
        counts: { class_availability: 1, teacher_availability: 1 },
        items: [
          {
            resource: 'class_availability',
            course_abbreviation: 'TGEI',
            class_name: 'TGEI 25/28',
            changed_blocks: 0,
            line: 2,
          },
          {
            resource: 'teacher_availability',
            teacher_name: 'Ana Silva',
            teacher_email: 'ana.silva@escola.pt',
            changed_blocks: 2,
            line: 3,
          },
        ],
      },
      issues: [],
    })
    renderPage()
    const classFile = new File(['x'], 'Cronos_DisponibilidadeTurmas_Template.csv', { type: 'text/csv' })
    const teacherFile = new File(['x'], 'Cronos_DisponibilidadeProfessores_Template.csv', { type: 'text/csv' })

    await user.upload(
      screen.getByLabelText('Selecionar ficheiro CSV de disponibilidade das turmas'),
      classFile,
    )
    await user.upload(
      screen.getByLabelText('Selecionar ficheiro CSV de disponibilidade dos professores'),
      teacherFile,
    )
    await user.click(screen.getByRole('button', { name: 'Verificar ficheiros' }))

    const classTable = await screen.findByRole('table', {
      name: 'Disponibilidade das turmas por turma',
    })
    const teacherTable = screen.getByRole('table', {
      name: 'Disponibilidade dos professores por professor',
    })
    expect(within(classTable).getByRole('columnheader', { name: 'Blocos que mudam' })).toBeInTheDocument()
    expect(within(teacherTable).getByRole('columnheader', { name: 'Blocos que mudam' })).toBeInTheDocument()
    expect(within(classTable).getByText('Sem alterações')).toBeInTheDocument()
    expect(within(teacherTable).getByText('2')).toBeInTheDocument()
  })

  it('renders every grid preview row without the 100 item cap', async () => {
    const user = userEvent.setup()
    const items = Array.from({ length: 120 }, (_, index) => ({
      resource: 'teacher_availability',
      teacher_name: `Professor ${index}`,
      teacher_email: `professor${index}@escola.pt`,
      changed_blocks: index % 3,
      line: index + 2,
    }))
    mocks.validate.mockResolvedValueOnce({
      can_commit: true,
      preview: { counts: { teacher_availability: 120 }, items },
      issues: [],
    })
    renderPage()
    const file = new File(['x'], 'Cronos_DisponibilidadeProfessores_Template.csv', { type: 'text/csv' })

    await user.upload(
      screen.getByLabelText('Selecionar ficheiro CSV de disponibilidade dos professores'),
      file,
    )
    await user.click(screen.getByRole('button', { name: 'Verificar ficheiros' }))

    const table = await screen.findByRole('table', {
      name: 'Disponibilidade dos professores por professor',
    })
    expect(within(table).getAllByRole('row')).toHaveLength(121)
    expect(within(table).getByText('Professor 119')).toBeInTheDocument()
  })

  it('shows a cell error with the actual column title', async () => {
    const user = userEvent.setup()
    mocks.validate.mockResolvedValueOnce({
      can_commit: false,
      preview: { counts: {}, items: [] },
      issues: [
        {
          code: 'hour_without_block',
          severity: 'error',
          resource: 'class_availability',
          line: 2,
          field: '08:30',
          message: 'Este dia não tem bloco às 08:30. Deixe a célula vazia.',
        },
      ],
    })
    renderPage()
    const file = new File(['x'], 'Cronos_DisponibilidadeTurmas_Template.csv', { type: 'text/csv' })

    await user.upload(
      screen.getByLabelText('Selecionar ficheiro CSV de disponibilidade das turmas'),
      file,
    )
    await user.click(screen.getByRole('button', { name: 'Verificar ficheiros' }))

    expect(
      await screen.findByText(
        'Disponibilidade das turmas, linha 2, 08:30: Este dia não tem bloco às 08:30. Deixe a célula vazia.',
      ),
    ).toBeInTheDocument()
  })

  it('supports selecting, checking and confirming the files', async () => {
    const user = userEvent.setup()
    renderPage()
    const file = new File(
      ['Nome da sala;Tipo de sala;Capacidade\r\nSala 1;Normal;20\r\n'],
      'Cronos_Salas_Template.csv',
      { type: 'text/csv' },
    )

    await user.upload(screen.getByLabelText('Selecionar ficheiro CSV de salas'), file)
    await user.click(screen.getByRole('button', { name: 'Verificar ficheiros' }))

    await waitFor(() => expect(screen.getByText('Resultado da verificação')).toBeInTheDocument())
    expect(screen.getByText('Salas: 1')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Confirmar importação' }))
    await waitFor(() => expect(mocks.commit).toHaveBeenCalledWith({ rooms: file }))
  })

  it('allows selecting the same file after removing it', async () => {
    const user = userEvent.setup()
    renderPage()
    const input = screen.getByLabelText('Selecionar ficheiro CSV de salas')
    const file = new File(['x'], 'salas.csv', { type: 'text/csv' })
    await user.upload(input, file)
    await user.click(within(cardFor('Salas')).getByRole('button', { name: 'Remover' }))
    expect(input.files).toHaveLength(0)
    await user.upload(input, file)
    expect(screen.getByText(/salas.csv/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Verificar ficheiros' }))
    expect(mocks.validate).toHaveBeenCalledWith({ rooms: file })
  })

  it('shows feedback when preparing a model fails', async () => {
    const user = userEvent.setup()
    mocks.download.mockRejectedValueOnce(new Error('offline'))
    renderPage()
    await user.click(downloadButtonForCard('Disponibilidade das turmas'))
    expect(await within(document.querySelector('[data-rht-toaster]')).findByText('Não foi possível preparar o modelo.')).toBeInTheDocument()
  })

  it('shows the exact message when the class availability model has no grid blocks', async () => {
    const user = userEvent.setup()
    mocks.download.mockRejectedValueOnce({
      response: {
        status: 400,
        data: { detail: { code: 'bad_request', context: { reason: 'no_grid_blocks' } } },
      },
    })
    renderPage()

    await user.click(downloadButtonForCard('Disponibilidade das turmas'))

    expect(
      await within(document.querySelector('[data-rht-toaster]')).findByText(
        'A escola ainda não configurou blocos.',
      ),
    ).toBeInTheDocument()
  })

  it('shows the exact message when the teacher availability model has no grid blocks', async () => {
    const user = userEvent.setup()
    mocks.download.mockRejectedValueOnce({
      response: {
        status: 400,
        data: { detail: { code: 'bad_request', context: { reason: 'no_grid_blocks' } } },
      },
    })
    renderPage()

    await user.click(downloadButtonForCard('Disponibilidade dos professores'))

    expect(
      await within(document.querySelector('[data-rht-toaster]')).findByText(
        'A escola ainda não configurou blocos.',
      ),
    ).toBeInTheDocument()
  })

  it('confirms only that the browser was asked to download and blocks duplicate requests', async () => {
    const user = userEvent.setup()
    let resolveDownload
    mocks.download.mockImplementation(() => new Promise((resolve) => { resolveDownload = resolve }))
    renderPage()

    await user.click(downloadButtonForCard('Disponibilidade das turmas'))
    expect(mocks.download).toHaveBeenCalledTimes(1)
    expect(screen.getByText('A preparar…')).toBeInTheDocument()

    await user.click(downloadButtonForCard('Disponibilidade dos professores'))
    expect(mocks.download).toHaveBeenCalledTimes(1)

    resolveDownload()
    expect(
      await within(document.querySelector('[data-rht-toaster]')).findByText(/Transferência iniciada/i)
    ).toBeInTheDocument()
  })

  it.each(['success', 'failure'])('suppresses a late download %s after changing school', async outcome => {
    const user = userEvent.setup()
    let finish
    mocks.download.mockImplementation(() => new Promise((resolve, reject) => {
      finish = () => outcome === 'success' ? resolve() : reject(new Error('offline'))
    }))
    setClerkState({ orgId: 'school_before' })
    const view = renderPage()
    await user.click(downloadButtonForCard('Disponibilidade das turmas'))
    expect(mocks.download).toHaveBeenCalledTimes(1)
    setClerkState({ orgId: 'school_after' })
    view.rerender(<MemoryRouter initialEntries={['/imports']}><BulkImport /></MemoryRouter>)
    await act(async () => { finish() })
    expect(screen.queryByText('Transferência iniciada. Verifique a pasta de transferências.')).not.toBeInTheDocument()
    expect(screen.queryByText('Não foi possível preparar o modelo.')).not.toBeInTheDocument()
    expect(screen.queryByText('A preparar…')).not.toBeInTheDocument()
  })
})
