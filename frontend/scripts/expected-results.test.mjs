import assert from 'node:assert/strict'
import test from 'node:test'
import { canonicalExecutedModules, canonicalProposalLessons, canonicalSchoolCalendar, validateImportedData, validateInitialTeacherProgress, validatePublishedTeacherWeek, validateExecutedLessonCredit, validateResetProtectedHistory } from '../e2e/utils/expected-results.js'

test('year reset preserves nonempty observed lesson history and refuses missing or changed references', () => {
  const history = { versionId: 3, rawLessons: [{ id: 9, assignment_id: 5, source_lesson_id: null,
    lesson_log_status: 'REVOKED', slices: [{ module_id: 7, minutes: 50, offset_minutes: 0 }] }], executed: [] }
  const witness = { slot: { scheduler_lesson_id: 9 }, revoked: { id: 11, operational_state: 'REVOKED', revoked_at: '2026-10-08T10:00:00Z' } }
  assert.equal(validateResetProtectedHistory(history, structuredClone(history), witness), 1)
  for (const corrupt of [value => { value.rawLessons = [] }, value => { value.versionId++ },
    value => { value.rawLessons[0].lesson_log_status = null }, value => { value.rawLessons[0].assignment_id++ },
    value => { value.rawLessons[0].slices[0].minutes++ }, value => { value.executed = [{ minutes: 50 }] }]) {
    const changed = structuredClone(history); corrupt(changed)
    assert.throws(() => validateResetProtectedHistory(history, changed, witness))
  }
  assert.throws(() => validateResetProtectedHistory(history, history, { ...witness, slot: { scheduler_lesson_id: 99 } }))
  assert.throws(() => validateResetProtectedHistory(history, history, { ...witness, revoked: { ...witness.revoked, revoked_at: null } }))
  assert.throws(() => validateResetProtectedHistory({ ...history, rawLessons: [] }, { ...history, rawLessons: [] }, witness))
})

test('ended lesson credit preserves identity and changes exactly the observed module minutes', () => {
  const before = { scheduler_lesson_id: 51, class_info: { id: 7 }, subject: { id: 8 }, teacher: { id: 9 },
    room: { id: 10 }, date: '2026-10-08', timeslot: { start_time: '09:00', end_time: '10:00' },
    ends_at: '2026-10-08T09:00:00Z', credit_minutes: 50, lesson_log_id: null, lesson_log_status: null,
    slices: [{ module_id: 11, offset_minutes: 40, minutes: 20, completed_minutes: 40, remaining_minutes: 20 },
      { module_id: 12, offset_minutes: 0, minutes: 30, completed_minutes: 0, remaining_minutes: 80 }] }
  const after = { ...structuredClone(before), lesson_log_id: 61, lesson_log_status: 'COMPLETED' }
  after.slices[0].completed_minutes = 60; after.slices[0].remaining_minutes = 0
  after.slices[1].completed_minutes = 30; after.slices[1].remaining_minutes = 50
  assert.equal(validateExecutedLessonCredit(before, after), 50)
  for (const corrupt of [value => { value.teacher.id = 99 }, value => { value.scheduler_lesson_id++ },
    value => { value.slices[0].completed_minutes++ }, value => { value.slices[1].remaining_minutes++ },
    value => { value.slices[0].offset_minutes++ }, value => { value.lesson_log_id = null }]) {
    const changed = structuredClone(after); corrupt(changed)
    assert.throws(() => validateExecutedLessonCredit(before, changed))
  }
  assert.throws(() => validateExecutedLessonCredit({ ...before, credit_minutes: 49 }, after))
})

function originalAndObserved() {
  const original = {
    rooms: { Lab: { type: 'Laboratório', capacity: 30 } },
    subjects: { Science: { room_type: 'Laboratório', modules: [{ name: 'First', code: 'S-01', order: 1, minutes: 90 }] } },
    teachers: { 'teacher@example.com': { name: 'Teacher', subjects: ['Science'] } },
    classes: [{ course: 'SCI', course_name: 'Science course', class: 'SCI 10', size: 25, grade_level: 10, start_year: 2026, end_year: 2029 }],
    demand: [{ course: 'SCI', class: 'SCI 10', subject: 'Science', teacher: 'teacher@example.com', minutes: 90 }],
    counts: { rooms: 1, subjects: 1, modules: 1, teachers: 1, courses: 1, classes: 1, assignments: 1 },
  }
  const schoolClass = { id: 30, organization_id: 7, course_id: 20, name: 'SCI 10', size: 25, grade_level: 10, start_year: 2026, end_year: 2029 }
  const observed = {
    organization_id: 7,
    rooms: [{ id: 1, organization_id: 7, name: 'Lab', type: 'lab', capacity: 30 }],
    subjects: [{ id: 10, organization_id: 7, name: 'Science', required_room_type: 'lab', modules: [{ id: 11, subject_id: 10, name: 'First', code: 'S-01', order: 0, hours_total: 1.5 }] }],
    teachers: [{ id: 40, organization_id: 7, name: 'Teacher', email: 'teacher@example.com', subject_ids: [10] }],
    classes: [schoolClass], courses: [{ id: 20, organization_id: 7, name: 'Science course', abbreviation: 'SCI', classes: [schoolClass], subjects: [{ id: 10, name: 'Science' }] }],
    classSubjects: [{ class_id: 30, class_name: 'SCI 10', course_name: 'Science course', course_abbreviation: 'SCI', grade_level: 10, subjects: [{ id: 50, subject_id: 10, subject_name: 'Science', required_room_type: 'lab', grade_level: 10, teacher_id: 40, teacher_name: 'Teacher' }] }],
  }
  return { original, observed }
}

test('published teacher weeks contain exactly the approved lessons and actual module slices', () => {
  const { original, observed } = originalAndObserved()
  const identities = validateImportedData(original, observed)
  const expected = [{ id: 501, assignment: ['SCI', 'SCI 10', 'Science'], teacher: 'teacher@example.com', room: 'Lab', date: '2026-10-26', start: '09:00', end: '10:00', credit_minutes: 45, slices: [{ module: 'S-01', offset: 30, minutes: 45 }] }]
  const row = { scheduler_lesson_id: 501, block_source: 'planned', date: '2026-10-26',
    timeslot: { id: 60, start_time: '09:00', end_time: '10:00' },
    subject: { id: 10, name: 'Science' }, teacher: { id: 40, name: 'Teacher' },
    room: { id: 1, name: 'Lab' }, class_info: { id: 30, name: 'SCI 10' },
    credit_minutes: 45, slices: [{ module_id: 11, module_name: 'First', offset_minutes: 30, minutes: 45, completed_minutes: 0, remaining_minutes: 90 }] }
  const verify = rows => validatePublishedTeacherWeek(original, identities, 40, '2026-10-26', rows, expected)
  assert.deepEqual(verify([row]), expected)
  assert.deepEqual(validatePublishedTeacherWeek(original, identities, 40, '2026-11-02', [], expected), [])
  for (const corrupt of [
    value => { value.teacher.id = 41 }, value => { value.room.name = 'Wrong room' },
    value => { value.class_info.id = 999 }, value => { value.subject.name = 'Wrong subject' },
    value => { value.scheduler_lesson_id = 999 }, value => { value.date = '2026-11-02' },
    value => { value.slices[0].minutes = 44 }, value => { value.credit_minutes = 44 },
    value => { value.slices[0].completed_minutes = 1 }, value => { value.slices[0].remaining_minutes = 89 },
    value => { value.slices[0].module_name = 'Wrong module' },
    value => { value.block_source = 'operational' },
  ]) {
    const changed = structuredClone(row)
    corrupt(changed)
    assert.throws(() => verify([changed]))
  }
  assert.throws(() => verify([]))
  assert.throws(() => verify([row, row]))
})

test('a new teacher session preserves the complete original curriculum without granting future credit', () => {
  const { original, observed } = originalAndObserved()
  const identities = validateImportedData(original, observed)
  const progress = [{ class_id: 30, class_name: 'SCI 10', course_name: 'Science course', grade_level: 10,
    subjects: [{ subject_id: 10, subject_name: 'Science', required_room_type: 'lab', total_hours: 1.5, completed_hours: 0, overall_percentage: 0,
      modules: [{ module_id: 11, module_name: 'First', module_code: 'S-01', hours_total: 1.5, hours_completed: 0, hours_debt: 0, is_completed: false, percentage: 0 }] }] }]
  const verify = value => validateInitialTeacherProgress(original, identities, 40, value)
  assert.equal(verify(progress).length, 1)
  for (const corrupt of [
    value => { value[0].class_id = 999 }, value => { value[0].grade_level = 11 },
    value => { value[0].subjects = [] }, value => { value[0].subjects[0].total_hours = 1 },
    value => { value[0].subjects[0].required_room_type = 'normal' },
    value => { value[0].subjects[0].modules[0].module_id = 999 },
    value => { value[0].subjects[0].modules[0].hours_completed = 1 },
    value => { value[0].subjects[0].modules[0].hours_debt = 1 },
    value => { value[0].subjects[0].modules[0].is_completed = true },
  ]) {
    const changed = structuredClone(progress)
    corrupt(changed)
    assert.throws(() => verify(changed))
  }
  assert.throws(() => verify([]))
})

test('proposal conversion preserves actual intervals and slices across Lisbon daylight saving time', () => {
  const { original, observed } = originalAndObserved()
  const identities = validateImportedData(original, observed)
  const lesson = { id: 501, assignment_id: 900, class_id: 30, subject_id: 10,
    teacher_id: 40, room_id: 1, school_date: '2026-10-23',
    starts_at: '2026-10-23T08:00:00Z', ends_at: '2026-10-23T09:00:00Z',
    physical_minutes: 60, credit_minutes: 45,
    slices: [{ module_id: 11, offset_minutes: 30, minutes: 45 }] }
  const convert = lessons => canonicalProposalLessons(original, identities, lessons, 'Europe/Lisbon')
  assert.deepEqual(convert([lesson]), [{ id: 501, assignment: ['SCI', 'SCI 10', 'Science'],
    teacher: 'teacher@example.com', room: 'Lab', date: '2026-10-23',
    start: '09:00', end: '10:00', credit_minutes: 45,
    slices: [{ module: 'S-01', offset: 30, minutes: 45 }] }])
  const winter = { ...lesson, id: 502, school_date: '2026-10-26',
    starts_at: '2026-10-26T08:00:00+00:00', ends_at: '2026-10-26T09:00:00+00:00' }
  assert.equal(convert([winter])[0].start, '08:00')
  assert.equal(convert([{ ...lesson, source_lesson_id: 400 }])[0].source_id, 400)
  assert.throws(() => convert([{ ...lesson, source_lesson_id: -1 }]), /origin/)
  for (const corrupt of [
    row => { row.class_id = 999 }, row => { row.teacher_id = 999 },
    row => { row.room_id = 999 }, row => { row.subject_id = 999 },
    row => { row.slices[0].module_id = 999 },
    row => { row.school_date = '2026-10-24' },
    row => { row.starts_at = '2026-10-23T08:00:00' },
    row => { row.starts_at = '2026-10-23T08:00:01Z' },
    row => { row.ends_at = '2026-10-24T09:00:00Z' },
    row => { row.physical_minutes = 59 },
    row => { row.assignment_id = 0 },
  ]) {
    const changed = structuredClone(lesson)
    corrupt(changed)
    assert.throws(() => convert([changed]))
  }
  assert.throws(() => convert([lesson, lesson]), /Duplicate/)
})

test('effective execution conversion binds exact module minutes to original assignments', () => {
  const { original, observed } = originalAndObserved()
  const identities = validateImportedData(original, observed)
  const entry = { assignment_id: 900, module_id: 11, minutes: 30 }
  const lesson = { assignment_id: 900, class_id: 30, subject_id: 10, teacher_id: 40 }
  const convert = rows => canonicalExecutedModules(original, identities, rows, [lesson])
  assert.deepEqual(convert([entry]), [{ assignment: ['SCI', 'SCI 10', 'Science'], module: 'S-01', minutes: 30 }])
  assert.deepEqual(convert([]), [])
  for (const corrupt of [{ assignment_id: 999 }, { module_id: 999 }, { minutes: 91 }, { minutes: 0 }, { minutes: true }, { minutes: 30.1 }]) {
    assert.throws(() => convert([{ ...entry, ...corrupt }]))
  }
  assert.throws(() => convert([entry, entry]), /duplicate/)
  assert.throws(() => canonicalExecutedModules(original, identities, [entry], [{ ...lesson, teacher_id: 999 }]))
  assert.throws(() => canonicalExecutedModules(original, identities, [entry], [{ ...lesson, class_id: 999 }]))
})

test('independent calendar preserves the full horizon, actual grid versions and mandatory unavailability', () => {
  const { original, observed } = originalAndObserved()
  const identities = validateImportedData(original, observed)
  const blocks = [0, 1, 2].map((day, i) => ({ id: 60 + i, day_of_week: day, start_time: '09:00:00', end_time: '10:00:00' }))
  const source = {
    organization_id: 7,
    year: { start_date: '2026-10-26', hard_end_date: '2026-10-28', preferred_end_date: '2026-10-28' },
    settings: { organization_id: 7, school_start_date: '2026-10-26', school_hard_end_date: '2026-10-28', preferred_end_date: '2026-10-28' },
    gridSettings: { organization_id: 7, lunch_window_start: '12:00:00', lunch_window_end: '14:00:00', lunch_min_duration_minutes: 60 },
    days: ['2026-10-26', '2026-10-27', '2026-10-28'].map((date, i) => ({ date, version_id: 100, blocks: [blocks[i]] })),
    events: [{ id: 80, organization_id: 7, event_type: 'national_holiday', start_date: '2026-10-26', end_date: '2026-10-26', class_ids: [] },
      { id: 81, organization_id: 7, event_type: 'internship_flow', start_date: '2026-10-27', end_date: '2026-10-27', class_ids: [30] }],
    availability: [{ version_id: 100, timeslots: blocks.map(row => ({ ...row, organization_id: 7 })), teachers: [{ teacher_id: 40,
      entries: blocks.map((row, i) => ({ timeslot_id: row.id, score: i === 1 ? -1 : 2 })) }] }],
  }
  const convert = value => canonicalSchoolCalendar(original, identities, value)
  const result = convert(source)
  assert.deepEqual(result.teaching_dates, ['2026-10-27', '2026-10-28'])
  assert.deepEqual(result.grid, { '2026-10-27': [['09:00', '10:00']], '2026-10-28': [['09:00', '10:00']] })
  assert.deepEqual(result.lunch, { start: '12:00', end: '14:00', minimum_minutes: 60 })
  assert.deepEqual(result.unavailable, [
    { kind: 'class', resource: ['SCI', 'SCI 10'], date: '2026-10-27', start: '00:00', end: '23:59' },
    { kind: 'teacher', resource: 'teacher@example.com', date: '2026-10-27', start: '09:00', end: '10:00' },
  ])
  for (const corrupt of [
    value => { value.days.pop() }, value => { value.days[1].date = value.days[0].date },
    value => { value.settings.organization_id = 8 }, value => { value.gridSettings.lunch_window_end = null },
    value => { value.events[1].class_ids = [999] }, value => { value.events[0].event_type = 'unknown' },
    value => { value.availability[0].teachers = [] },
    value => { value.availability[0].teachers[0].entries.pop() },
    value => { value.availability[0].teachers[0].entries[0].score = 3 },
    value => { value.days[1].version_id = 999 },
    value => { value.days[1].blocks[0].start_time = '08:00:00' },
  ]) {
    const changed = structuredClone(source)
    corrupt(changed)
    assert.throws(() => convert(changed))
  }
  const transition = structuredClone(source)
  transition.days[2].version_id = 101
  transition.days[2].blocks[0].id = 72
  transition.availability.push({ version_id: 101,
    timeslots: [{ ...transition.days[2].blocks[0], organization_id: 7 }],
    teachers: [{ teacher_id: 40, entries: [{ timeslot_id: 72, score: -1 }] }] })
  assert.deepEqual(convert(transition).unavailable.at(-1), { kind: 'teacher', resource: 'teacher@example.com', date: '2026-10-28', start: '09:00', end: '10:00' })
})

test('independent import comparison checks full content and references, not merely row totals', () => {
  const { original, observed } = originalAndObserved()
  const identities = validateImportedData(original, observed)
  assert.equal(identities.teachers['teacher@example.com'], 40)
  assert.equal(identities.assignments['SCI/SCI 10/Science'], 50)
  const corruptions = [
    value => { value.rooms[0].capacity = 20 },
    value => { value.rooms[0].organization_id = 8 },
    value => { value.subjects[0].modules[0].subject_id = 999 },
    value => { value.subjects[0].modules[0].name = 'Wrong' },
    value => { value.subjects[0].modules[0].hours_total = 2 },
    value => { value.teachers[0].subject_ids = [] },
    value => { value.classes[0].grade_level = 11 },
    value => { value.classSubjects[0].subjects[0].teacher_id = 999 },
    value => { value.classSubjects[0].subjects.push({ ...value.classSubjects[0].subjects[0] }) },
    value => { value.courses[0].name = 'Wrong course' },
    value => { value.courses[0].classes[0] = { ...value.courses[0].classes[0], size: 99 } },
    value => { value.classSubjects[0].class_name = 'Wrong class' },
    value => { value.classSubjects[0].course_abbreviation = 'Wrong course' },
    value => { value.classSubjects = [] },
  ]
  for (const corrupt of corruptions) {
    const changed = structuredClone(observed)
    corrupt(changed)
    assert.throws(() => validateImportedData(original, changed))
  }
  assert.deepEqual(validateImportedData(original, observed), identities)
})

test('assignment identities cannot be reused across classes and ordering cannot change the result', () => {
  const { original, observed } = originalAndObserved()
  original.classes.push({ ...original.classes[0], class: 'SCI 11', grade_level: 11 })
  original.demand.push({ ...original.demand[0], class: 'SCI 11' })
  original.counts.classes = original.counts.assignments = 2
  const nextClass = { ...observed.classes[0], id: 31, name: 'SCI 11', grade_level: 11 }
  observed.classes.push(nextClass)
  observed.courses[0].classes.push(nextClass)
  observed.classSubjects.push({ ...observed.classSubjects[0], class_id: 31, class_name: 'SCI 11', grade_level: 11, subjects: [{ ...observed.classSubjects[0].subjects[0], grade_level: 11 }] })
  assert.throws(() => validateImportedData(original, observed), /identity/)
  observed.classSubjects[1].subjects[0].id = 51
  const before = validateImportedData(original, observed)
  observed.classes.reverse()
  observed.classSubjects.reverse()
  assert.deepEqual(validateImportedData(original, observed), before)
})
