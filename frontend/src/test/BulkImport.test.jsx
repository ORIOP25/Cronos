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

  it('presents plain-language instructions without technical implementation terms', () => {
    renderPage()

    expect(screen.getByRole('heading', { name: 'Importar dados' })).toBeInTheDocument()
    expect(screen.getByText('Descarregue o modelo da secção pretendida.')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Descarregar modelo' })).toHaveLength(6)
    expect(screen.queryByText(/UTF-8|BOM|backend|atómica|Recurso|JSON/i)).not.toBeInTheDocument()
  })

  it('lists the class availability section with its instructions', () => {
    renderPage()

    expect(screen.getByText('Disponibilidade das turmas')).toBeInTheDocument()
    expect(
      screen.getByText('Cada linha é uma turma num dia. Cada coluna de hora é um bloco.'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Não apague colunas de hora. Se a grelha mudar, descarregue um modelo novo.'),
    ).toBeInTheDocument()
    expect(
      screen.getByLabelText('Selecionar ficheiro CSV de disponibilidade das turmas'),
    ).toBeInTheDocument()
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

  it('shows feedback when preparing a model fails', async () => {
    const user = userEvent.setup()
    mocks.download.mockRejectedValueOnce(new Error('offline'))
    renderPage()
    await user.click(screen.getAllByRole('button', { name: 'Descarregar modelo' }).at(-1))
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

    await user.click(screen.getAllByRole('button', { name: 'Descarregar modelo' }).at(-1))

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

    const buttons = screen.getAllByRole('button', { name: 'Descarregar modelo' })
    await user.click(buttons[0])
    expect(mocks.download).toHaveBeenCalledTimes(1)
    expect(screen.getByText('A preparar…')).toBeInTheDocument()

    await user.click(buttons[1])
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
    await user.click(screen.getAllByRole('button', { name: 'Descarregar modelo' })[0])
    expect(mocks.download).toHaveBeenCalledTimes(1)
    setClerkState({ orgId: 'school_after' })
    view.rerender(<MemoryRouter initialEntries={['/imports']}><BulkImport /></MemoryRouter>)
    await act(async () => { finish() })
    expect(screen.queryByText('Transferência iniciada. Verifique a pasta de transferências.')).not.toBeInTheDocument()
    expect(screen.queryByText('Não foi possível preparar o modelo.')).not.toBeInTheDocument()
    expect(screen.queryByText('A preparar…')).not.toBeInTheDocument()
  })
})
