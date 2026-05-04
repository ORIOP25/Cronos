/** Dados mock para testes E2E do dashboard. */
export const today = new Date().toISOString().slice(0, 10)

export const dashboardComplete = {
  alerts: {
    pending_occurrences_today: 3,
    pending_timesheets: 5,
    pending_drafts: 1,
    active_substitutions_today: 2,
  },
  resources: {
    teachers_count: 47,
    classes_count: 12,
    courses_count: 4,
    subjects_count: 95,
    rooms_count: 30,
    rooms_by_type: { normal: 16, lab: 8, gym: 3, art: 3 },
  },
  schedule_health: {
    generation_id: 'abc123def456789',
    blocks_count: 1247,
    classes_total: 6,
    classes_empty_week: 2,
    week_slots_avg: 28.5,
    duplicate_teacher_slots: 0,
    duplicate_class_slots: 0,
    weekly_fairness_spread: 3.2,
    teacher_week_slots_avg: 22.1,
  },
  class_progress: [
    { class_id: 1, class_name: '1ºA Téc. Aux.', course_id: 1, course_name: 'TAuxSau', grade_level: 10, overall_percentage: 38, completed_hours: 19, total_hours: 50 },
    { class_id: 2, class_name: '1ºB TGPSI', course_id: 2, course_name: 'TGPSI', grade_level: 10, overall_percentage: 42, completed_hours: 21, total_hours: 50 },
    { class_id: 3, class_name: '1ºA TGPSI', course_id: 2, course_name: 'TGPSI', grade_level: 10, overall_percentage: 64, completed_hours: 32, total_hours: 50 },
    { class_id: 4, class_name: '2ºA TGPSI', course_id: 2, course_name: 'TGPSI', grade_level: 11, overall_percentage: 91, completed_hours: 45.5, total_hours: 50 },
  ],
  debts: {
    total_gaps: 12,
    total_hours_owed: 34,
    total_gaps_overdue: 4,
    total_hours_owed_overdue: 8,
    affected_classes_count: 4,
    as_of_date: today,
  },
  organization_name: 'Escola Profissional de Teste',
}

export const dashboardWithAlerts = {
  ...dashboardComplete,
  alerts: {
    pending_occurrences_today: 3,
    pending_timesheets: 5,
    pending_drafts: 1,
    active_substitutions_today: 0,
  },
}

export const dashboardAllClear = {
  ...dashboardComplete,
  alerts: {
    pending_occurrences_today: 0,
    pending_timesheets: 0,
    pending_drafts: 0,
    active_substitutions_today: 0,
  },
}

export const dashboardEmptyOrg = {
  ...dashboardComplete,
  alerts: {
    pending_occurrences_today: 0,
    pending_timesheets: 0,
    pending_drafts: 0,
    active_substitutions_today: 0,
  },
  resources: {
    teachers_count: 0,
    classes_count: 0,
    courses_count: 0,
    subjects_count: 0,
    rooms_count: 0,
    rooms_by_type: {},
  },
  schedule_health: null,
  class_progress: [],
  debts: {
    total_gaps: 0,
    total_hours_owed: 0,
    total_gaps_overdue: 0,
    total_hours_owed_overdue: 0,
    affected_classes_count: 0,
    as_of_date: today,
  },
}

export const dashboardNoGeneration = {
  ...dashboardComplete,
  schedule_health: null,
}

/** Heatmap mock data — evita que o componente quebre. */
export const heatmapData = [
  { day_of_week: 0, start_time: '09:00', available_count: 8, total_teachers: 10 },
  { day_of_week: 0, start_time: '09:45', available_count: 7, total_teachers: 10 },
]

export const timeslotsData = [
  { id: 1, day_of_week: 0, start_time: '09:00', end_time: '09:45' },
  { id: 2, day_of_week: 0, start_time: '09:45', end_time: '10:30' },
]
