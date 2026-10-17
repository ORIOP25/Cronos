export function getRoomType(type) {
  return { label: typeof type === 'string' ? type || '—' : type?.name || '—', color: 'secondary' }
}

export function formatGradeLevel(gradeLevel) {
  return gradeLevel == null || gradeLevel === '' ? '—' : `${gradeLevel}.º ano`
}

const TIMESHEET_STATUSES = Object.freeze({
  OPEN: { label: 'Aberta', color: 'secondary', background: '#f8f9fa' },
  SUBMITTED: { label: 'Submetida', color: 'info', background: '#fff3cd' },
  APPROVED: { label: 'Aprovada', color: 'success', background: '#d1e7dd' },
})

export function getTimesheetStatus(status) {
  return TIMESHEET_STATUSES[status] ?? { label: status || '—', color: 'secondary', background: '#e7f1ff' }
}

const LESSON_LOG_STATUSES = Object.freeze({
  PENDING: { label: 'Planeado', stateClass: 'zen-state-planned', badge: 'secondary' },
  COMPLETED: { label: 'Concluída ✓', stateClass: 'zen-state-given', badge: 'success' },
  OCCURRENCE: { label: 'Ocorrência', stateClass: 'zen-state-gap', badge: 'warning' },
})

export function getLessonLogStatus(status) {
  return LESSON_LOG_STATUSES[status] ?? LESSON_LOG_STATUSES.PENDING
}

export const GENERATION_STATUS_LABELS = Object.freeze({
  QUEUED: 'Geração em fila',
  RUNNING: 'A gerar horário',
  CANCEL_REQUESTED: 'A cancelar geração',
  CANCELED: 'Geração cancelada',
  SUCCEEDED: 'Rascunho pronto para revisão',
  NO_VALID_OUTPUT: 'Não foi possível gerar um horário válido',
  FAILED: 'Erro na geração',
})
