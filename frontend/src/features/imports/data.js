import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useOrganization } from '@clerk/react'
import { useApiClient } from '../../ApiClientContext'
import { invalidatePreparationQueries } from '../readiness/data'
import { invalidateOrgQueries } from '../queryKeys'

export const IMPORT_RESOURCES = Object.freeze([
  {
    key: 'rooms',
    label: 'Salas',
    filename: 'Cronos_Salas_Template.csv',
    origin: '/rooms',
    instructions: [
      'Cada linha cria uma sala.',
      'Nome da sala: nome único, por exemplo Sala 1.02.',
      'Tipo de sala: escreva o nome do tipo. Um nome que a escola ainda não tem cria um tipo novo.',
      'Capacidade: número de pessoas, igual ou superior a 1.',
    ],
    fields: { name: 'Nome da sala', type: 'Tipo de sala', capacity: 'Capacidade' },
  },
  {
    key: 'subjects',
    label: 'Disciplinas e módulos',
    filename: 'Cronos_DisciplinasEModulos_Template.csv',
    origin: '/subjects',
    instructions: [
      'Repita a disciplina numa nova linha por cada módulo.',
      'Tipo de sala: escreva o nome do tipo. Um nome que a escola ainda não tem cria um tipo novo.',
      'Horas e ordem são números inteiros a partir de 1.',
      'A ordem dos módulos deve ser contínua: 1, 2, 3…',
      'Para criar uma disciplina sem módulos, deixe os campos do módulo vazios; será apresentado um aviso.',
      'Se começar a preencher um módulo, preencha todos os campos desse módulo.',
    ],
    fields: {
      name: 'Nome da disciplina',
      required_room_type: 'Tipo de sala',
      module_name: 'Nome do módulo',
      module_code: 'Código do módulo',
      module_hours: 'Horas do módulo',
      module_order: 'Ordem do módulo',
    },
  },
  {
    key: 'courses',
    label: 'Cursos e turmas',
    filename: 'Cronos_CursosETurmas_Template.csv',
    origin: '/courses',
    instructions: [
      'Repita a sigla e o nome do curso numa nova linha por cada turma.',
      'O ano escolar deve ser 10, 11 ou 12.',
      'Os anos de início e fim usam quatro algarismos; o ano final deve ser posterior ao inicial.',
      'O número de alunos deve ser igual ou superior a 1.',
      'Sala da turma: vazio quer dizer Automática. Use uma sala existente ou do ficheiro de salas; só se aplica a turmas novas.',
      'A sala da turma deve ter lugares para todos os alunos da turma.',
      'Para criar apenas o curso, deixe os campos da turma vazios; será apresentado um aviso.',
    ],
    fields: {
      abbreviation: 'Sigla do curso',
      name: 'Nome do curso',
      class_name: 'Nome da turma',
      grade_level: 'Ano escolar',
      start_year: 'Ano de início',
      end_year: 'Ano de fim',
      size: 'Número de alunos',
      home_room: 'Sala da turma',
    },
  },
  {
    key: 'teachers',
    label: 'Professores e competências',
    filename: 'Cronos_ProfessoresECompetencias_Template.csv',
    origin: '/members',
    instructions: [
      'Use uma linha por disciplina que o professor pode lecionar.',
      'Repita o mesmo nome e email quando o professor tiver várias disciplinas.',
      'A disciplina deve já existir ou estar incluída nos ficheiros selecionados.',
      'Deixar a disciplina vazia cria o professor sem competências e apresenta um aviso.',
      'Esta secção serve apenas para professores novos.',
    ],
    fields: {
      name: 'Nome do professor',
      email: 'Email do professor',
      competency_subject: 'Nome da disciplina',
    },
  },
  {
    key: 'assignments',
    label: 'Atribuições',
    filename: 'Cronos_Atribuicoes_Template.csv',
    origin: '/courses',
    instructions: [
      'Cada linha associa uma disciplina a uma turma.',
      'Use exatamente a sigla, turma e disciplina existentes ou incluídas nos ficheiros selecionados.',
      'O email do professor é opcional.',
      'Quando indicado, deve corresponder a um professor incluído nos ficheiros selecionados.',
      'Sem email, a atribuição é criada sem professor e apresenta um aviso.',
    ],
    fields: {
      course_abbreviation: 'Sigla do curso',
      class_name: 'Nome da turma',
      subject_name: 'Nome da disciplina',
      teacher_email: 'Email do professor',
    },
  },
  {
    key: 'class_availability',
    label: 'Disponibilidade das turmas',
    filename: 'Cronos_DisponibilidadeTurmas_Template.csv',
    origin: '/courses',
    instructions: [
      'O modelo já traz as turmas, as horas da grelha e a disponibilidade atual.',
      'Cada linha é uma turma num dia. Cada coluna de hora é um bloco.',
      'Escreva Impossível, Evitar, Neutro ou Preferencial. Uma célula vazia conta como Neutro.',
      'Cada turma do ficheiro fica com a grelha do ficheiro. As turmas que não aparecem ficam iguais.',
      'Não apague colunas de hora. Se a grelha mudar, descarregue um modelo novo.',
    ],
    fields: {
      course_abbreviation: 'Sigla do curso',
      class_name: 'Nome da turma',
      day: 'Dia',
    },
  },
  {
    key: 'teacher_availability',
    label: 'Disponibilidade dos professores',
    filename: 'Cronos_DisponibilidadeProfessores_Template.csv',
    origin: '/members',
    instructions: [
      'O modelo já traz os professores ativos, as horas da grelha e a disponibilidade atual.',
      'Cada linha é um professor num dia. Cada coluna de hora é um bloco.',
      'O email identifica o professor. O nome serve só para ler o ficheiro.',
      'Escreva Impossível, Evitar, Neutro ou Preferencial. Uma célula vazia conta como Neutro.',
      'Cada professor do ficheiro fica com a grelha do ficheiro. Os professores que não aparecem ficam iguais.',
      'Não apague colunas de hora. Se a grelha mudar, descarregue um modelo novo.',
    ],
    fields: {
      teacher_name: 'Nome do professor',
      teacher_email: 'Email do professor',
      day: 'Dia',
    },
  },
  {
    key: 'teacher_presence',
    label: 'Presença dos professores',
    filename: 'Cronos_PresencaProfessores_Template.csv',
    origin: '/members',
    instructions: [
      'O modelo já traz os professores ativos e a regra atual.',
      'O email identifica o professor; pode já existir ou vir no ficheiro de Professores.',
      'Hora de almoço: Sim ou Não. Uma célula vazia vale Sim.',
      'Deixe o mínimo em branco para não definir uma regra. Se definir um mínimo e deixar o tempo máximo sem aulas em branco, aplica-se 1 hora.',
      'Cada linha substitui os três valores desse professor. Os professores ausentes ficam iguais.',
    ],
    fields: {
      name: 'Nome do professor',
      email: 'Email do professor',
      lunch: 'Hora de almoço',
      minimum_hours: 'Mínimo de horas por presença',
      max_gap_hours: 'Tempo máximo sem aulas (horas)',
    },
  },
])

const IMPORT_COUNT_LABELS = Object.freeze({
  room_types: 'Tipos de sala novos',
  rooms: 'Salas',
  subjects: 'Disciplinas',
  modules: 'Módulos',
  courses: 'Cursos',
  classes: 'Turmas',
  teachers: 'Professores',
  competencies: 'Competências',
  assignments: 'Atribuições',
  class_availability: 'Disponibilidade das turmas',
  teacher_availability: 'Disponibilidade dos professores',
  teacher_presence: 'Presença dos professores',
})

function getImportResource(resource) {
  return IMPORT_RESOURCES.find((item) => item.key === resource)
}

function getImportResourceLabel(resource) {
  return getImportResource(resource)?.label || 'Secção'
}

function getImportFieldLabel(resource, field) {
  return getImportResource(resource)?.fields?.[field] || field || 'Campo'
}

export function getImportCountLabel(resource) {
  return IMPORT_COUNT_LABELS[resource] || resource
}

export function formatImportIssue(issue) {
  const parts = [getImportResourceLabel(issue.resource)]
  if (issue.line) parts.push(`linha ${issue.line}`)
  if (issue.field) parts.push(getImportFieldLabel(issue.resource, issue.field))
  return `${parts.join(', ')}: ${issue.message}`
}

const IMPORT_INVALIDATIONS = [
  'members', 'teachers', 'eligible-teachers', 'rooms', 'room-types', 'subjects', 'courses',
  'classes', 'class-subjects', 'available-subjects', 'class-availability',
  'teacher-availability', 'teacher-presence', 'substitute-recommendations',
  'substitute-diagnostics', 'occurrences', 'teacher-progress', 'my-availability',
  'my-presence', 'heatmap', 'dashboard', 'readiness', 'scheduler-status',
]

function fileError(code, message) {
  const error = new Error(message)
  error.code = code
  return error
}

export async function fileToBase64(file) {
  const bytes = new Uint8Array(await file.arrayBuffer())
  let binary = ''
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    binary += String.fromCodePoint(...bytes.subarray(offset, offset + 0x8000))
  }
  return btoa(binary)
}

export async function filesToPayload(files) {
  const entries = await Promise.all(Object.entries(files)
    .filter(([, file]) => file)
    .map(async ([resource, file]) => [resource, {
      filename: file.name,
      content_base64: await fileToBase64(file),
    }]))
  return Object.fromEntries(entries)
}

function csvValue(value) {
  const text = String(value ?? '')
  const safe = /^[=+\-@]/.test(text) ? `'${text}` : text
  return `"${safe.replaceAll('"', '""')}"`
}

export function createBulkImportReport(issues) {
  const rows = [
    ['Tipo', 'Secção', 'Linha', 'Campo', 'Mensagem'],
    ...issues.map((issue) => [
      issue.severity === 'warning' ? 'Aviso' : 'Erro',
      getImportResourceLabel(issue.resource),
      issue.line || '',
      issue.field ? getImportFieldLabel(issue.resource, issue.field) : '',
      issue.message,
    ]),
  ]
  const csv = rows.map((row) => row.map(csvValue).join(';')).join('\r\n') + '\r\n'
  return new Blob([`\ufeff${csv}`], { type: 'text/csv;charset=utf-8' })
}

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

function errorBodyBytes(data) {
  if (ArrayBuffer.isView(data)) {
    return new Uint8Array(data.buffer, data.byteOffset, data.byteLength)
  }
  if (data instanceof ArrayBuffer || Object.prototype.toString.call(data) === '[object ArrayBuffer]') {
    return new Uint8Array(data)
  }
  return null
}

// The template request uses responseType "arraybuffer", so a structured JSON error
// arrives as raw bytes. Decode only a JSON body with a detail object and reattach it
// so the shared error formatter can read code/context/reference. Anything else is
// left untouched, and no raw text is ever surfaced.
function normalizeTemplateError(error) {
  const bytes = errorBodyBytes(error?.response?.data)
  if (bytes) {
    try {
      const payload = JSON.parse(new TextDecoder().decode(bytes))
      if (payload && typeof payload === 'object' && !Array.isArray(payload)
        && payload.detail && typeof payload.detail === 'object') {
        error.response.data = payload
      }
    } catch {
      // Not JSON: keep the original error untouched.
    }
  }
  return error
}

export async function downloadBulkImportTemplate(apiClient, resource) {
  const definition = getImportResource(resource)
  if (!definition) throw fileError('resource_unknown', 'Secção de importação desconhecida.')
  let bytes
  try {
    bytes = await apiClient.get(`/imports/templates/${resource}`, { responseType: 'arraybuffer' })
  } catch (error) {
    throw normalizeTemplateError(error)
  }
  downloadBlob(new Blob([bytes], { type: 'text/csv;charset=utf-8' }), definition.filename)
}

function invalidateImports(queryClient, orgId) {
  return Promise.all([
    invalidateOrgQueries(queryClient, orgId, IMPORT_INVALIDATIONS),
    invalidatePreparationQueries(queryClient, orgId),
  ])
}

export function useValidateBulkImport() {
  const apiClient = useApiClient()
  return useMutation({
    mutationFn: async (files) => apiClient.post('/imports/validate', { files: await filesToPayload(files) }),
  })
}

export function useCommitBulkImport() {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id
  return useMutation({
    mutationFn: async (files) => apiClient.post('/imports/commit', { files: await filesToPayload(files) }),
    onSuccess: () => invalidateImports(queryClient, orgId),
  })
}
