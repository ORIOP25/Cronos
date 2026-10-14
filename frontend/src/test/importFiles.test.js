import { describe, expect, it, vi } from 'vitest'
import {
  createBulkImportReport,
  fileToBase64,
  filesToPayload,
  formatImportIssue,
  getImportCountLabel,
  IMPORT_RESOURCES,
} from '../features/imports/data'

function csvFile(content, name = 'Cronos_Salas_Template.csv') {
  return new File([content], name, { type: 'text/csv' })
}

describe('bulk import file utilities', () => {
  it('converts files with and without UTF-8 BOM to base64', async () => {
    const file = csvFile('\ufeffNome da sala;Tipo de sala;Capacidade\r\nSala;Normal;20\r\n')
    const fileWithoutBom = csvFile('Nome da sala;Tipo de sala;Capacidade\r\nSala;Normal;20\r\n')

    await expect(fileToBase64(file)).resolves.toBe(
      '77u/Tm9tZSBkYSBzYWxhO1RpcG8gZGUgc2FsYTtDYXBhY2lkYWRlDQpTYWxhO05vcm1hbDsyMA0K',
    )
    await expect(fileToBase64(fileWithoutBom)).resolves.toBe(
      'Tm9tZSBkYSBzYWxhO1RpcG8gZGUgc2FsYTtDYXBhY2lkYWRlDQpTYWxhO05vcm1hbDsyMA0K',
    )
  })

  it('builds the backend payload without changing selected files', async () => {
    const rooms = csvFile('\ufeffNome da sala;Tipo de sala;Capacidade\r\nSala;Normal;20\r\n')
    const subjects = csvFile('\ufeffNome da disciplina;Tipo de sala;Nome do módulo;Código do módulo;Horas do módulo;Ordem do módulo\r\nDisciplina;Normal;;;;\r\n', 'Cronos_DisciplinasEModulos_Template.csv')

    await expect(filesToPayload({ rooms, subjects })).resolves.toEqual({
      rooms: { filename: 'Cronos_Salas_Template.csv', content_base64: expect.any(String) },
      subjects: { filename: 'Cronos_DisciplinasEModulos_Template.csv', content_base64: expect.any(String) },
    })
  })

  it('creates an Excel-safe semicolon issue report with a BOM', () => {
    const report = createBulkImportReport([
      { severity: 'error', resource: 'rooms', line: 2, field: 'name', code: 'x', message: '=unsafe' },
    ])

    expect(report).toBeInstanceOf(Blob)
    expect(report.type).toBe('text/csv;charset=utf-8')
    return report.text().then((text) => {
      expect(text).toContain('"Tipo";"Secção";"Linha";"Campo";"Mensagem"')
      expect(text).toContain('"Erro";"Salas";"2";"Nome da sala";"\'=unsafe"')
      expect(text).not.toContain(';x;')
    })
  })

  it('exposes the Portuguese names, instructions and count labels', () => {
    expect(IMPORT_RESOURCES.map((item) => item.filename)).toEqual([
      'Cronos_Salas_Template.csv',
      'Cronos_DisciplinasEModulos_Template.csv',
      'Cronos_CursosETurmas_Template.csv',
      'Cronos_ProfessoresECompetencias_Template.csv',
      'Cronos_Atribuicoes_Template.csv',
      'Cronos_DisponibilidadeTurmas_Template.csv',
    ])
    expect(IMPORT_RESOURCES.every((item) => item.instructions.length > 0)).toBe(true)
    expect(IMPORT_RESOURCES[0].instructions.join(' ')).toContain('Normal')
    expect(IMPORT_RESOURCES[1].instructions.join(' ')).toContain('Laboratório')
    expect(getImportCountLabel('rooms')).toBe('Salas')
    expect(getImportCountLabel('assignments')).toBe('Atribuições')
    expect(getImportCountLabel('class_availability')).toBe('Disponibilidade das turmas')
  })

  it('formats issues with Portuguese section and field names', () => {
    expect(formatImportIssue({
      resource: 'rooms', line: 4, field: 'type', message: 'Escreva Normal, Laboratório, Ginásio ou Artes.',
    })).toBe('Salas, linha 4, Tipo de sala: Escreva Normal, Laboratório, Ginásio ou Artes.')
  })

  it('shows the raw column title when the field is a dynamic hour column', () => {
    expect(formatImportIssue({
      resource: 'class_availability', line: 3, field: '08:30', message: 'Este dia não tem bloco às 08:30. Deixe a célula vazia.',
    })).toBe(
      'Disponibilidade das turmas, linha 3, 08:30: Este dia não tem bloco às 08:30. Deixe a célula vazia.',
    )
  })

  it('revokes object URLs after downloading a report', async () => {
    const createObjectURL = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test')
    const revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    const click = vi.fn()
    vi.spyOn(document, 'createElement').mockReturnValue({
      href: '', download: '', click,
    })

    const report = createBulkImportReport([])
    const { downloadBlob } = await import('../features/imports/data')
    downloadBlob(report, 'issues.csv')

    expect(click).toHaveBeenCalled()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:test')
    createObjectURL.mockRestore()
    revokeObjectURL.mockRestore()
  })
})
