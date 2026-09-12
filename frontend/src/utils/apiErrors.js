import { humanizeOperationalDetail, TXT } from './terminology'

const PRESENTATIONS = {
  authentication_required: { title: 'Sessão terminada', message: 'A sua sessão terminou. Entre novamente para continuar.', retryable: true },
  access_forbidden: { title: 'Acesso não disponível', message: 'Não tem permissão para realizar esta ação.' },
  resource_not_found: { title: 'Não encontramos esse recurso', message: 'O recurso pedido já não existe ou não está disponível.' },
  conflict: { title: 'Os dados foram alterados', message: 'Atualize a página e tente novamente.', retryable: true },
  validation_error: { title: 'Reveja os dados', message: 'Reveja os dados indicados e tente novamente.' },
  bad_request: { title: 'Não foi possível concluir', message: 'Não foi possível processar o pedido.' },
  too_many_requests: { title: 'Aguarde um momento', message: 'Foram efetuadas demasiadas tentativas. Aguarde e tente novamente.', retryable: true },
  service_unavailable: { title: 'Serviço temporariamente indisponível', message: 'Tente novamente dentro de instantes.', retryable: true },
  unexpected_error: { title: 'Algo correu mal', message: 'Ocorreu um erro inesperado. Tente novamente.', retryable: true, supportRequired: true },
  request_body_too_large: { title: 'Pedido demasiado grande', message: 'Reduza os dados enviados e tente novamente.' },
  preflight_failed: { title: 'A geração precisa de configuração', message: 'Reveja os bloqueios indicados antes de gerar o horário.' },
  generation_dispatch_failed: { title: 'Geração não iniciada', message: 'Não foi possível iniciar a geração do horário. Tente novamente.', retryable: true },
  CANCELED: { title: 'Geração cancelada', message: 'A geração foi cancelada. Pode iniciar uma nova geração.', retryable: true },
  TIMED_OUT: { title: 'Geração demorou demasiado', message: 'A geração excedeu o limite de cinco minutos. Os dados e o horário aprovado foram preservados.', retryable: true },
  NO_VALID_OUTPUT: { title: 'Não foi possível gerar um horário válido', message: 'Reveja a disponibilidade e as regras da escola antes de tentar novamente.' },
  FAILED_VALIDATION: { title: 'Rascunho rejeitado', message: 'O rascunho gerado foi rejeitado antes da publicação. Reveja a configuração.' },
  SYSTEM_ERROR: { title: 'Problema durante a geração', message: 'Ocorreu um problema inesperado durante a geração. Tente novamente.', retryable: true, supportRequired: true },
  DISPATCH_STALLED: { title: 'Geração em espera', message: 'A geração não chegou ao serviço de execução. Tente novamente.', retryable: true, supportRequired: true },
  WORKER_STALLED: { title: 'Execução interrompida', message: 'A execução da geração foi interrompida. Tente novamente.', retryable: true, supportRequired: true },
  FAILED: { title: 'Erro na geração', message: 'Ocorreu um problema inesperado durante a geração. Tente novamente.', retryable: true, supportRequired: true },
  member_sync_error: { title: 'Sincronização pendente', message: 'A sincronização do acesso está pendente. Tente novamente dentro de instantes.', retryable: true, supportRequired: true },
  invitation_delivery_failed: { title: 'Convite não enviado', message: 'Não foi possível enviar o convite. Tente novamente dentro de instantes.', retryable: true },
  HOLIDAY_SYNC_FAILED: { title: 'Calendário não sincronizado', message: 'Não foi possível sincronizar os feriados. Desative a sincronização automática ou tente novamente.', retryable: true },
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

export function getApiErrorPresentation(error, context = 'generic') {
  const detail = detailOf(error)
  const detailObject = detail && typeof detail === 'object' && !Array.isArray(detail) ? detail : {}
  const code = detailObject.code || STATUS_CODES[error?.response?.status] || null
  const candidates = code ? [code] : (CONTEXT_FALLBACKS[context] || CONTEXT_FALLBACKS.generic)
  const knownCode = candidates.find((candidate) => PRESENTATIONS[candidate]) || 'unexpected_error'
  const copy = PRESENTATIONS[knownCode]
  return {
    code: code || knownCode,
    title: isNetworkError(error) ? 'Ligação indisponível' : copy.title,
    message: isNetworkError(error)
      ? 'Não foi possível ligar ao servidor. Verifique a ligação e tente novamente.'
      : humanizeOperationalDetail(copy.message),
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
