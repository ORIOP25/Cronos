/**
 * Terminologia padronizada para toda a interface do Cronos.
 * Centraliza as palavras usadas em botões, labels e mensagens.
 * Idioma: PT-PT (Português de Portugal), tratamento formal.
 */

export const TXT = {
  // Ações
  SAVE: 'Guardar',
  SAVING: 'A guardar…',
  CANCEL: 'Cancelar',
  REMOVE: 'Remover',
  EDIT: 'Editar',
  CREATE: 'Criar',
  ADD: 'Adicionar',
  CONFIRM: 'Confirmar',
  REVERT: 'Reverter',
  DELETE: 'Remover',
  CONFIRM_DELETE: 'Confirmar Remoção',
  CONFIRM_DELETE_MESSAGE: 'Tem a certeza de que deseja remover este registo? Esta ação não pode ser desfeita.',

  // Estados
  LOADING: 'A carregar…',
  EMPTY_TABLE: 'Ainda sem registos.',
  EMPTY_TABLE_HINT: 'Os dados aparecerão aqui assim que forem criados.',
  NO_RESULTS: 'Nenhum resultado encontrado.',
  NO_RESULTS_FILTER: 'Sem resultados para os filtros selecionados.',
  ERROR_LOADING: 'Erro ao carregar os dados. Verifique a ligação e tente novamente.',
  ERROR_SAVING: 'Erro ao guardar. Tente novamente.',
  ERROR_DELETING: 'Erro ao remover. Este registo pode estar associado a outros elementos.',
  ERROR_UNKNOWN: 'Ocorreu um erro inesperado. Tente novamente.',

  // Aulas
  LESSON_GIVEN: 'Aula Dada',
  LESSON_ABSENT: 'Registar Falta',
  LESSON_PENDING: 'Pendente',
  LESSON_SUBSTITUTED: 'Substituída',
  LESSON_PLANNED: 'Planeado',
  LESSON_FUTURE: 'Esta aula ainda não terminou. O registo estará disponível após a hora de término.',

  // Substituições
  SUBSTITUTION: 'Substituição',
  SUBSTITUTION_START: 'Iniciar Substituição',
  SUBSTITUTION_CONFIRM: 'Confirmar Substituição',

  // Fecho Semanal
  WEEK_SUBMIT_CONFIRM: 'Tem a certeza de que deseja submeter esta semana? Após a submissão, não poderá fazer alterações.',
  WEEK_APPROVED: 'Semana Aprovada',
  WEEK_SUBMITTED: 'Semana Submetida',
  WEEK_OPEN: 'Em Aberto',
  WEEK_REOPEN: 'Reabrir Semana',
  WEEK_REOPEN_CONFIRM: 'Tem a certeza de que deseja reabrir esta semana? O professor poderá editar as aulas novamente.',

  // Geração de Horários
  GENERATION_PENDING: 'A preparar cálculo do horário…',
  GENERATION_FETCHING: 'A ler dados da escola…',
  GENERATION_SOLVING: 'A calcular o melhor horário para a escola…',
  GENERATION_SOLVING_SUBTITLE: 'Pode demorar alguns minutos.',
  GENERATION_EXPANDING: 'A expandir para datas reais…',
  GENERATION_SAVING: 'A guardar solução…',
  GENERATION_CANCELED: 'Cancelado.',
  GENERATION_SUCCESS: 'Concluído!',
  GENERATION_FAILURE: 'Erro na geração.',
  GENERATION_MOTOR: 'motor de cálculo',
  GENERATION_SERVER: 'servidor de processamento',

  // Ocorrências
  OCCURRENCE_GIVEN: 'Dada',
  OCCURRENCE_GAP: 'Furo',
  OCCURRENCE_SUBSTITUTED: 'Substituída',
  OCCURRENCE_DECIDED: 'Decidida',
  OCCURRENCE_PENDING_DECISION: 'Pendente de decisão',

  // Calendário
  CALENDAR_NATIONAL_HOLIDAY: 'Feriado Nacional',
  CALENDAR_SCHOOL_BREAK: 'Pausa Escolar',
  CALENDAR_EXAM_PERIOD: 'Período de Exames',
  CALENDAR_OTHER: 'Outro',

  // Modo
  MODE_CLASS_VIEW: 'Turma',
  MODE_TEACHER_VIEW: 'Professor',

  // Rascunhos
  DRAFT_PENDING: 'Rascunho de Reparação Pendente',
  DRAFT_APPROVE: 'Aprovar e Ativar',
  DRAFT_REJECT: 'Rejeitar',
  DRAFT_ADDED: 'blocos adicionados',
  DRAFT_REMOVED: 'blocos removidos',
  DRAFT_UNCHANGED: 'sem alteração',
  DRAFT_SUMMARY: 'Resumo Estatístico (vs Atual)',
  DRAFT_DELTA_DAYS: 'Fim das aulas',
  DRAFT_BACKLOG: 'Por agendar',
  DRAFT_GAPS: 'Furos',
  DRAFT_CHURN: 'Alterações (futuro)',
  DRAFT_SPREAD: 'Dispersão fim',

  // Preferências
  PREFERENCE_PREFERRED: 'Preferencial',
  PREFERENCE_NEUTRAL: 'Neutro',
  PREFERENCE_AVOID: 'Evitar',
  PREFERENCE_IMPOSSIBLE: 'Impossível',

  // Geral
  HOME: 'Painel de Controlo',
  BRAND_TAGLINE: 'Gestão escolar inteligente e sem stress.',
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
  other: TXT.CALENDAR_OTHER,
}

/**
 * Cores de estado operacional (dada / furo / substituída).
 */
export const OPERATIONAL_STATE_LABELS = {
  OPEN_PENDING: 'Pendente',
  DECIDED_GIVEN: 'Dada',
  DECIDED_GAP: 'Furo',
  DECIDED_SUBSTITUTED: 'SubstituÃ­da',
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
