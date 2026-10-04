import { humanizeOperationalDetail, TXT } from './terminology'
import { getRoomType } from './presentation'

const PRESENTATIONS = {
  authentication_required: { title: 'Sessão terminada', message: 'A sua sessão terminou. Entre novamente para continuar.', retryable: true },
  access_forbidden: { title: 'Acesso não disponível', message: 'Não tem permissão para realizar esta ação.' },
  resource_not_found: { title: 'Não encontrámos o que procura', message: 'O item pedido já não existe ou não está disponível.' },
  conflict: { title: 'Os dados foram alterados', message: 'Atualize a página e tente novamente.', retryable: true },
  resource_in_use: { title: 'Em utilização', message: 'Este item está a ser utilizado no horário atual. Remova ou republique o horário primeiro.' },
  course_has_classes: { title: 'Turmas atuais', message: 'Apague primeiro as turmas atuais deste curso.' },
  validation_error: { title: 'Reveja os dados', message: 'Reveja os dados indicados e tente novamente.' },
  bad_request: { title: 'Não foi possível concluir', message: 'Não foi possível concluir o pedido. Tente novamente.' },
  too_many_requests: { title: 'Aguarde um momento', message: 'Foram efetuadas demasiadas tentativas. Aguarde e tente novamente.', retryable: true },
  service_unavailable: { title: 'Serviço temporariamente indisponível', message: 'Tente novamente dentro de instantes.', retryable: true },
  unexpected_error: { title: 'Algo correu mal', message: 'Ocorreu um erro inesperado. Tente novamente.', retryable: true, supportRequired: true },
  request_body_too_large: { title: 'Pedido demasiado grande', message: 'Reduza os dados enviados e tente novamente.' },
  preflight_failed: { title: 'A geração precisa de configuração', message: 'Reveja os bloqueios indicados antes de gerar o horário.' },
  NO_ELIGIBLE_ROOM: { title: 'Salas incompatíveis', message: 'Existem turmas sem sala compatível com o tipo e a lotação. Ajuste as salas e tente novamente.' },
  generation_dispatch_failed: { title: 'Geração não iniciada', message: 'Não foi possível iniciar a geração do horário. Tente novamente.', retryable: true },
  CANCELED: { title: 'Geração cancelada', message: 'A geração foi cancelada. Pode iniciar uma nova geração.', retryable: true },
  TIMED_OUT: { title: 'Geração demorou demasiado', message: 'A geração excedeu o limite de cinco minutos. Os dados e o horário aprovado foram preservados.', retryable: true },
  NO_VALID_OUTPUT: { title: 'Não foi possível gerar um horário válido', message: 'Reveja a disponibilidade e as regras da escola antes de tentar novamente.' },
  FAILED_VALIDATION: { title: 'Rascunho rejeitado', message: 'O rascunho gerado foi rejeitado antes da publicação. Reveja a configuração.' },
  SYSTEM_ERROR: { title: 'Problema durante a geração', message: 'Ocorreu um problema inesperado durante a geração. Tente novamente.', retryable: true, supportRequired: true },
  DISPATCH_STALLED: { title: 'Geração em espera', message: 'A geração ainda não começou. Tente novamente.', retryable: true, supportRequired: true },
  WORKER_STALLED: { title: 'Execução interrompida', message: 'A execução da geração foi interrompida. Tente novamente.', retryable: true, supportRequired: true },
  FAILED: { title: 'Erro na geração', message: 'Ocorreu um problema inesperado durante a geração. Tente novamente.', retryable: true, supportRequired: true },
  member_sync_error: { title: 'Acesso por confirmar', message: 'O acesso ainda está a ser confirmado. Tente novamente dentro de instantes.', retryable: true, supportRequired: true },
  invitation_delivery_failed: { title: 'Convite não enviado', message: 'Não foi possível enviar o convite. Tente novamente dentro de instantes.', retryable: true },
  HOLIDAY_SYNC_FAILED: { title: 'Feriados não atualizados', message: 'Não foi possível obter os feriados. Desative a atualização automática ou tente novamente.', retryable: true },
  CALENDAR_EVENT_CONFIRMATION_REQUIRED: { title: 'Confirmação necessária', message: 'O estágio remove aulas do horário. Pré-visualize e confirme a alteração.' },
  CALENDAR_EVENT_STALE: { title: 'O horário mudou', message: 'As aulas afetadas mudaram desde a pré-visualização. Repita a pré-visualização antes de guardar.', retryable: true },
  INTERNSHIP_FLOW_INVALID: { title: 'Dados do fluxo inválidos', message: 'Verifique o ano letivo, as datas e se selecionou apenas turmas ativas da escola.' },
  teacher_competency_missing: { title: 'Competência não atribuída', message: 'O professor não tem competência para lecionar esta disciplina.' },
  duplicate_timeslot: { title: 'Horário repetido', message: 'A disponibilidade contém um horário duplicado. Reveja os horários e tente novamente.' },
  LEGAL_ACCEPTANCE_REQUIRED: { title: 'Aceitação necessária', message: 'A organização deve aceitar os documentos legais antes de continuar.' },
  FOUNDATION_REQUIRED: { title: 'Configuração ainda não concluída', message: 'Conclua a configuração inicial da escola antes de continuar.' },
}

const STATUS_CODES = { 400: 'bad_request', 401: 'authentication_required', 403: 'access_forbidden', 404: 'resource_not_found', 409: 'conflict', 422: 'validation_error', 429: 'too_many_requests' }
const CONTEXT_FALLBACKS = {
  auth: ['authentication_required', 'unexpected_error'],
  organization: ['access_forbidden', 'service_unavailable'],
  'team.load': ['service_unavailable', 'resource_not_found'],
  'team.invite': ['invitation_delivery_failed', 'service_unavailable'],
  'team.sync': ['member_sync_error', 'service_unavailable'],
  'schedule.load': ['service_unavailable'],
  'schedule.generate': ['generation_dispatch_failed', 'service_unavailable'],
  'schedule.approve': ['conflict', 'service_unavailable'],
  generic: ['unexpected_error'],
}

const detailOf = (error) => error?.response?.data?.detail

export function getApiErrorCode(error) {
  const detail = detailOf(error)
  return detail && typeof detail === 'object' && !Array.isArray(detail) ? detail.code || null : null
}

const isNetworkError = (error) => error?.code === 'ERR_NETWORK'
  || (!error?.response && /network error/i.test(error?.message || ''))

const responseRequestId = (error) => {
  const headers = error?.response?.headers
  if (!headers) return null
  return headers['x-request-id'] || headers['X-Request-ID'] || null
}

const ROOM_REASONS = new Set(['NO_ROOM_OF_TYPE', 'INSUFFICIENT_CAPACITY', 'SPECIFIC_ROOM_RESTRICTION'])

const isText = (value) => typeof value === 'string' && value.length > 0
const isPositiveInt = (value) => Number.isInteger(value) && value > 0

function formatRoomIssue(issue) {
  if (!issue || typeof issue !== 'object') return null
  const { class_name: className, subject_name: subjectName, reason } = issue
  if (!isText(className) || !isText(subjectName) || !ROOM_REASONS.has(reason)) return null
  const roomType = getRoomType(issue.required_room_type).label
  if (reason === 'NO_ROOM_OF_TYPE') {
    return `${className} / ${subjectName}: não existe sala do tipo ${roomType}.`
  }
  if (!isPositiveInt(issue.required_capacity)) return null
  if (reason === 'INSUFFICIENT_CAPACITY') {
    if (!isPositiveInt(issue.max_available_capacity)) return null
    return (
      `${className} / ${subjectName}: ${issue.required_capacity} alunos, ` +
      `mas a maior sala (${roomType}) tem ${issue.max_available_capacity} lugares.`
    )
  }
  return (
    `${className} / ${subjectName}: as salas permitidas não têm ` +
    `${issue.required_capacity} lugares.`
  )
}

function formatRoomIssues(errorContext) {
  const issues = Array.isArray(errorContext?.room_issues) ? errorContext.room_issues : []
  const lines = issues.map(formatRoomIssue).filter(Boolean)
  if (lines.length === 0) return null
  return `${lines.join('\n')}\nCorrija a lotação em Salas ou as regras de sala e tente novamente.`
}

export function getApiErrorPresentation(error, context = 'generic') {
  const detail = detailOf(error)
  const detailObject = detail && typeof detail === 'object' && !Array.isArray(detail) ? detail : {}
  const statusCode = error?.response?.status
  const detailCode = detailObject.code && PRESENTATIONS[detailObject.code] ? detailObject.code : null
  // An unrecognized code leans on the status: 422 reads as validation, while
  // internal failures keep the generic message instead of a specific one.
  const statusFallback = statusCode >= 500 ? 'unexpected_error' : STATUS_CODES[statusCode]
  const code = detailCode || statusFallback || null
  const candidates = code ? [code] : (CONTEXT_FALLBACKS[context] || CONTEXT_FALLBACKS.generic)
  const knownCode = candidates.find((candidate) => PRESENTATIONS[candidate]) || 'unexpected_error'
  const copy = PRESENTATIONS[knownCode]
  const roomMessage = knownCode === 'NO_ELIGIBLE_ROOM' ? formatRoomIssues(detailObject.context) : null
  return {
    code: code || knownCode,
    title: isNetworkError(error) ? 'Ligação indisponível' : copy.title,
    message: isNetworkError(error)
      ? 'Não foi possível ligar. Verifique a ligação e tente novamente.'
      : humanizeOperationalDetail(roomMessage || copy.message),
    reference: typeof detailObject.reference === 'string' ? detailObject.reference : responseRequestId(error),
    retryable: detailObject.retryable ?? copy.retryable ?? false,
    supportRequired: detailObject.support_required ?? copy.supportRequired ?? false,
  }
}

export function getApiErrorMessage(error, fallbackMessage = TXT.ERROR_UNKNOWN, context = 'generic') {
  const presentation = getApiErrorPresentation(error, context)
  if (!error?.response && !error?.code && fallbackMessage) return fallbackMessage
  return presentation.message
}
