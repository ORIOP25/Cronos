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
      'Cronos_DisponibilidadeProfessores_Template.csv',
      'Cronos_PresencaProfessores_Template.csv',
    ])
    expect(IMPORT_RESOURCES.every((item) => item.instructions.length > 0)).toBe(true)
    expect(IMPORT_RESOURCES[0].instructions.join(' ')).toContain('cria um tipo novo')
    expect(IMPORT_RESOURCES[1].instructions.join(' ')).toContain('cria um tipo novo')
    expect(getImportCountLabel('room_types')).toBe('Tipos de sala novos')
    expect(getImportCountLabel('rooms')).toBe('Salas')
    expect(getImportCountLabel('assignments')).toBe('Atribuições')
    expect(getImportCountLabel('class_availability')).toBe('Disponibilidade das turmas')
    expect(getImportCountLabel('teacher_availability')).toBe('Disponibilidade dos professores')
    expect(getImportCountLabel('teacher_presence')).toBe('Presença dos professores')
  })

  it('describes the optional home room column of the classes template', () => {
    const courses = IMPORT_RESOURCES.find((item) => item.key === 'courses')

    expect(Object.keys(courses.fields)).toEqual([
      'abbreviation', 'name', 'class_name', 'grade_level', 'start_year', 'end_year', 'size', 'home_room',
    ])
    expect(courses.fields.home_room).toBe('Sala da turma')
    expect(courses.instructions).toContain(
      'Sala da turma: vazio quer dizer Automática. Use uma sala existente ou do ficheiro de salas; só se aplica a turmas novas.',
    )
  })

  it('defines the teacher availability resource right after the class availability resource', () => {
    const keys = IMPORT_RESOURCES.map((item) => item.key)
    const classIndex = keys.indexOf('class_availability')
    expect(keys[classIndex + 1]).toBe('teacher_availability')

    const resource = IMPORT_RESOURCES[classIndex + 1]
    expect(resource.label).toBe('Disponibilidade dos professores')
    expect(resource.filename).toBe('Cronos_DisponibilidadeProfessores_Template.csv')
    expect(resource.origin).toBe('/members')
    expect(resource.fields).toEqual({
      teacher_name: 'Nome do professor',
      teacher_email: 'Email do professor',
      day: 'Dia',
    })
    expect(resource.instructions).toEqual([
      'O modelo já traz os professores ativos, as horas da grelha e a disponibilidade atual.',
      'Cada linha é um professor num dia. Cada coluna de hora é um bloco.',
      'O email identifica o professor. O nome serve só para ler o ficheiro.',
      'Escreva Impossível, Evitar, Neutro ou Preferencial. Uma célula vazia conta como Neutro.',
      'Cada professor do ficheiro fica com a grelha do ficheiro. Os professores que não aparecem ficam iguais.',
      'Não apague colunas de hora. Se a grelha mudar, descarregue um modelo novo.',
    ])
  })

  it('formats issues with Portuguese section and field names', () => {
    expect(formatImportIssue({
      resource: 'rooms', line: 4, field: 'type', message: 'Escreva o tipo de sala.',
    })).toBe('Salas, linha 4, Tipo de sala: Escreva o tipo de sala.')
  })

  it('shows the raw column title when the field is a dynamic hour column', () => {
    expect(formatImportIssue({
      resource: 'class_availability', line: 3, field: '08:30', message: 'Este dia não tem bloco às 08:30. Deixe a célula vazia.',
    })).toBe(
      'Disponibilidade das turmas, linha 3, 08:30: Este dia não tem bloco às 08:30. Deixe a célula vazia.',
    )
  })

  it('formats a teacher availability email issue with the Portuguese field name', () => {
    expect(formatImportIssue({
      resource: 'teacher_availability', line: 5, field: 'teacher_email', message: 'Não existe nenhum professor com este email.',
    })).toBe(
      'Disponibilidade dos professores, linha 5, Email do professor: Não existe nenhum professor com este email.',
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
