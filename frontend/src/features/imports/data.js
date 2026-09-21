import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useOrganization } from '@clerk/react'
import { useApiClient } from '../../ApiClientContext'
import { invalidatePreparationQueries } from '../readiness/data'
import { invalidateOrgQueries } from '../queryKeys'

export const IMPORT_RESOURCES = Object.freeze([
  { key: 'rooms', label: 'Salas', filename: 'salas.csv', origin: '/rooms' },
  { key: 'subjects', label: 'Disciplinas e módulos', filename: 'disciplinas.csv', origin: '/subjects' },
  { key: 'courses', label: 'Cursos e turmas', filename: 'cursos.csv', origin: '/courses' },
  { key: 'teachers', label: 'Professores e competências', filename: 'professores.csv', origin: '/members' },
  { key: 'assignments', label: 'Atribuições', filename: 'atribuicoes.csv', origin: '/courses' },
])

const IMPORT_INVALIDATIONS = [
  'members', 'teachers', 'eligible-teachers', 'rooms', 'subjects', 'courses',
  'classes', 'class-subjects', 'available-subjects', 'dashboard', 'readiness', 'scheduler-status',
]

function fileError(code, message) {
  const error = new Error(message)
  error.code = code
  return error
}

function hasUtf8Bom(bytes) {
  return bytes.length >= 3 && bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf
}

export async function fileToBase64(file) {
  const bytes = new Uint8Array(await file.arrayBuffer())
  if (!hasUtf8Bom(bytes)) throw fileError('utf8_bom_required', 'O ficheiro deve usar UTF-8 com BOM.')
  let binary = ''
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000))
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
    ['severity', 'resource', 'line', 'field', 'code', 'message'],
    ...issues.map((issue) => [issue.severity, issue.resource, issue.line, issue.field, issue.code, issue.message]),
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

export async function downloadBulkImportTemplate(apiClient, resource) {
  const definition = IMPORT_RESOURCES.find((item) => item.key === resource)
  if (!definition) throw fileError('resource_unknown', 'Recurso de importação desconhecido.')
  const bytes = await apiClient.get(`/imports/templates/${resource}`, { responseType: 'arraybuffer' })
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
