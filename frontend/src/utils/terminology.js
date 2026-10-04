/**
 * Terminologia padronizada para toda a interface do Cronos.
 * Centraliza as palavras usadas em botões, labels e mensagens.
 * Idioma: PT-PT (Português de Portugal), tratamento formal.
 */

export const TXT = {
  SAVING: 'A guardar…',
  CANCEL: 'Cancelar',
  REMOVE: 'Remover',
  EDIT: 'Editar',
  ADD: 'Adicionar',
  CONFIRM: 'Confirmar',
  CONFIRM_DELETE: 'Confirmar Remoção',
  CONFIRM_DELETE_MESSAGE: 'Tem a certeza de que deseja remover este registo? Esta ação não pode ser desfeita.',
  LOADING: 'A carregar…',
  EMPTY_TABLE: 'Ainda sem registos.',
  EMPTY_TABLE_HINT: 'Os dados aparecerão aqui assim que forem criados.',
  ERROR_LOADING: 'Erro ao carregar os dados. Verifique a ligação e tente novamente.',
  ERROR_SAVING: 'Erro ao guardar. Tente novamente.',
  ERROR_UNKNOWN: 'Ocorreu um erro inesperado. Tente novamente.',
  RECORD_ARCHIVED: 'Registo arquivado. O histórico (horários, sumários e progresso) foi preservado.',
  RECORD_REMOVED: 'Registo removido.',
  CLASS_ARCHIVED: 'Turma arquivada. O histórico (horários, sumários e progresso) foi preservado.',
  CLASS_REMOVED: 'Turma removida.',
  WEEK_SUBMIT_CONFIRM: 'Tem a certeza de que deseja submeter esta semana? Após a submissão, não poderá fazer alterações.',
  WEEK_REOPEN_CONFIRM: 'Tem a certeza de que deseja reabrir esta semana? O professor poderá editar as aulas novamente.',
  GENERATION_MOTOR: 'gerador de horários',
  GENERATION_SERVER: 'serviço de geração',
  OCCURRENCE_PENDING_DECISION: 'Pendente de decisão',
  CALENDAR_NATIONAL_HOLIDAY: 'Feriado Nacional',
  CALENDAR_SCHOOL_BREAK: 'Pausa Escolar',
  CALENDAR_EXAM_PERIOD: 'Período de Exames',
  CALENDAR_INTERNSHIP_FLOW: 'Fluxo de Estágio',
  CALENDAR_OTHER: 'Outro',
  SIDEBAR_BRAND: 'Cronos',
}

/**
 * Humaniza termos técnicos do motor de cálculo para linguagem do domínio escolar.
 * @param {string} detail
 * @returns {string}
 */
export function humanizeOperationalDetail(detail) {
  if (typeof detail !== 'string' || !detail.trim()) return detail
  return detail
    .replace(/\(fase intensiva\)/gi, '')
    .replace(/CP-SAT/gi, TXT.GENERATION_MOTOR)
    .replace(/solver/gi, TXT.GENERATION_MOTOR)
    .replace(/worker/gi, TXT.GENERATION_SERVER)
}

/**
 * Tipos de evento de calendário em formato legível.
 */
export const EVENT_TYPE_LABELS = {
  national_holiday: TXT.CALENDAR_NATIONAL_HOLIDAY,
  school_break: TXT.CALENDAR_SCHOOL_BREAK,
  exam_period: TXT.CALENDAR_EXAM_PERIOD,
  internship_flow: TXT.CALENDAR_INTERNSHIP_FLOW,
  other: TXT.CALENDAR_OTHER,
}

/**
 * Cores de estado operacional (dada / furo / substituída).
 */
export const OPERATIONAL_STATE_LABELS = {
  OPEN_PENDING: 'Pendente',
  DECIDED_GIVEN: 'Dada',
  DECIDED_GAP: 'Furo',
  DECIDED_SUBSTITUTED: 'Substituída',
  CLOSED: 'Resolvida',
  REVOKED: 'Revertida',
}

export const OPERATIONAL_STATE_COLORS = {
  OPEN_PENDING: 'warning',
  DECIDED_GIVEN: 'success',
  DECIDED_GAP: 'danger',
  DECIDED_SUBSTITUTED: 'warning',
  CLOSED: 'secondary',
  REVOKED: 'secondary',
}
