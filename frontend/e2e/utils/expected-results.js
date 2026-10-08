import { isDeepStrictEqual } from 'node:util'

const roomTypes = { normal: 'normal', laboratorio: 'lab', ginasio: 'gym', artes: 'art', lab: 'lab', gym: 'gym', art: 'art' }
const roomType = value => roomTypes[String(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()]
const sorted = values => [...values].sort((left, right) => JSON.stringify(left).localeCompare(JSON.stringify(right)))

export function validateResetProtectedHistory(before, after, witness) {
  const lesson = before.rawLessons?.find(row => row.id === witness?.slot?.scheduler_lesson_id)
  if (!lesson || lesson.lesson_log_status !== 'REVOKED' || !lesson.slices?.length
    || !Number.isSafeInteger(witness?.revoked?.id) || witness.revoked.id <= 0
    || witness.revoked.operational_state !== 'REVOKED'
    || !witness.revoked.revoked_at || !Number.isFinite(Date.parse(witness.revoked.revoked_at))) {
    throw new Error('Reset requires nonempty history from the observed UI reversal')
  }
  for (const field of ['versionId', 'rawLessons', 'executed']) {
    if (!isDeepStrictEqual(before[field], after[field])) throw new Error(`Reset changed protected lesson history: ${field}`)
  }
  return before.rawLessons.length
}

export function validateExecutedLessonCredit(before, after) {
  for (const field of ['scheduler_lesson_id', 'class_info', 'subject', 'teacher', 'room', 'date', 'timeslot', 'ends_at', 'credit_minutes']) {
    if (!isDeepStrictEqual(before[field], after[field])) throw new Error(`Execution changed physical lesson identity: ${field}`)
  }
  if (!Number.isSafeInteger(after.lesson_log_id) || after.lesson_log_id <= 0 || after.lesson_log_status !== 'COMPLETED') throw new Error('Completed lesson log is missing')
  if (!Number.isSafeInteger(before.credit_minutes) || before.credit_minutes <= 0 || !before.slices?.length || after.slices?.length !== before.slices.length) throw new Error('Exact curricular credit is unavailable')
  let minutes = 0
  for (let index = 0; index < before.slices.length; index++) {
    const previous = before.slices[index], current = after.slices[index]
    if (!Number.isSafeInteger(previous.minutes) || previous.minutes <= 0 || previous.completed_minutes !== previous.offset_minutes
      || previous.remaining_minutes < previous.minutes) throw new Error('Lesson does not match the actual execution frontier')
    const expected = { ...previous, completed_minutes: previous.completed_minutes + previous.minutes,
      remaining_minutes: previous.remaining_minutes - previous.minutes }
    if (!isDeepStrictEqual(current, expected)) throw new Error('Completed module credit is not the exact lesson delta')
    minutes += previous.minutes
  }
  if (minutes !== before.credit_minutes) throw new Error('Module slices do not match lesson credit')
  return minutes
}

function schoolDay(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) throw new Error('Invalid observed school date')
  const date = new Date(`${value}T00:00:00Z`)
  if (Number.isNaN(date.valueOf()) || date.toISOString().slice(0, 10) !== value) throw new Error('Invalid observed school date')
  return date
}

export function schoolDateRange(start, end) {
  const first = schoolDay(start), last = schoolDay(end)
  if (first > last) throw new Error('Invalid observed school date bounds')
  const dates = []
  for (let cursor = first.getTime(); cursor <= last.getTime(); cursor += 86_400_000) {
    dates.push(new Date(cursor).toISOString().slice(0, 10))
  }
  return dates
}

function minuteTime(value) {
  if (typeof value !== 'string' || !/^(?:[01]\d|2[0-3]):[0-5]\d(?::00(?:\.0+)?)?$/.test(value)) throw new Error('Grid times must use whole minutes')
  return value.slice(0, 5)
}

function originalTeacherEmail(identities, teacherId) {
  const email = Object.entries(identities.teachers).find(([, id]) => id === teacherId)?.[0]
  if (!email) throw new Error('Teacher session references an unknown original profile')
  return email
}

export function validatePublishedTeacherWeek(original, identities, teacherId, weekStart, observed, approved) {
  const email = originalTeacherEmail(identities, teacherId)
  const first = schoolDay(weekStart)
  if (first.getUTCDay() !== 1) throw new Error('Published teacher weeks must start on Monday')
  const last = new Date(first)
  last.setUTCDate(last.getUTCDate() + 6)
  const end = last.toISOString().slice(0, 10)
  const expected = approved.filter(lesson => lesson.teacher === email && lesson.date >= weekStart && lesson.date <= end)
  const lessons = observed.map(slot => {
    const demand = original.demand.find(row => identities.classes[`${row.course}/${row.class}`] === slot.class_info?.id && identities.subjects[row.subject] === slot.subject?.id && row.teacher === email)
    const room = Object.keys(original.rooms).find(name => identities.rooms[name] === slot.room?.id)
    if (!demand || !room || slot.block_source !== 'planned' || slot.teacher?.id !== teacherId || slot.teacher.name !== original.teachers[email].name || slot.room.name !== room || slot.subject.name !== demand.subject || slot.class_info.name !== demand.class || !Number.isSafeInteger(slot.timeslot.id) || slot.timeslot.id <= 0) throw new Error('Published week has different teacher, resources or provenance')
    const modules = original.subjects[demand.subject].modules
    return { id: slot.scheduler_lesson_id, assignment: [demand.course, demand.class, demand.subject],
      teacher: email, room, date: slot.date, start: minuteTime(slot.timeslot.start_time), end: minuteTime(slot.timeslot.end_time), credit_minutes: slot.credit_minutes,
      slices: slot.slices.map(slice => {
        const module = modules.find(module => identities.modules[`${demand.subject}/${module.code}`] === slice.module_id)
        if (!module || slice.module_name !== module.name || slice.completed_minutes !== 0 || slice.remaining_minutes !== module.minutes) throw new Error('Published week has an unknown module or unexpected executed credit')
        return { module: module.code, offset: slice.offset_minutes, minutes: slice.minutes }
      }) }
  })
  requireEqual(lessons, expected, 'published teacher week')
  return lessons
}

export function validateInitialTeacherProgress(original, identities, teacherId, observed) {
  const email = originalTeacherEmail(identities, teacherId)
  const expected = original.demand.filter(row => row.teacher === email)
  const classes = index(observed.map(row => ({ ...row, id: row.class_id })), 'teacher progress classes')
  const assignments = []
  for (const schoolClass of classes.values()) {
    const source = original.classes.find(row => identities.classes[`${row.course}/${row.class}`] === schoolClass.class_id)
    if (!source || schoolClass.class_name !== source.class || schoolClass.course_name !== source.course_name || schoolClass.grade_level !== source.grade_level) throw new Error('Teacher progress has inconsistent class metadata')
    for (const subject of index(schoolClass.subjects.map(row => ({ ...row, id: row.subject_id })), 'teacher progress subjects').values()) {
      const demand = expected.find(row => row.course === source.course && row.class === source.class && identities.subjects[row.subject] === subject.subject_id)
      if (!demand || subject.subject_name !== demand.subject || roomType(subject.required_room_type) !== roomType(original.subjects[demand.subject].room_type) || subject.total_hours * 60 !== demand.minutes || subject.completed_hours !== 0 || subject.overall_percentage !== 0) throw new Error('Teacher progress differs from the original assignment or grants future credit')
      const modules = index(subject.modules.map(row => ({ ...row, id: row.module_id })), 'teacher progress modules')
      requireEqual([...modules.values()].map(module => [module.module_id, module.module_code, module.module_name, module.hours_total * 60, module.hours_completed, module.hours_debt, module.is_completed, module.percentage]),
        original.subjects[demand.subject].modules.map(module => [identities.modules[`${demand.subject}/${module.code}`], module.code, module.name, module.minutes, 0, 0, false, 0]), 'initial teacher module progress')
      assignments.push([demand.course, demand.class, demand.subject])
    }
  }
  requireEqual(assignments, expected.map(row => [row.course, row.class, row.subject]), 'complete teacher progress assignments')
  return assignments
}

export function canonicalSchoolCalendar(original, identities, source) {
  const { organization_id: organizationId, year, settings, gridSettings, days, events, availability } = source
  if (!Number.isSafeInteger(organizationId) || organizationId <= 0 || settings.organization_id !== organizationId || gridSettings.organization_id !== organizationId) throw new Error('Calendar configuration belongs to another school')
  if (settings.school_start_date !== year.start_date || settings.school_hard_end_date !== year.hard_end_date || settings.preferred_end_date !== year.preferred_end_date) throw new Error('School settings and scheduler dates differ')
  const dates = schoolDateRange(year.start_date, year.hard_end_date)
  if (year.preferred_end_date != null) {
    schoolDay(year.preferred_end_date)
    if (year.preferred_end_date < year.start_date || year.preferred_end_date > year.hard_end_date) throw new Error('Preferred end date is outside the school horizon')
  }
  requireEqual(days.map(day => day.date), dates, 'complete grid horizon')
  const classes = new Map(original.classes.map(row => [identities.classes[`${row.course}/${row.class}`], [row.course, row.class]]))
  const teachers = new Map(Object.entries(identities.teachers).map(([email, id]) => [id, email]))
  const versions = new Map()
  const signature = slot => [slot.id, slot.day_of_week, minuteTime(slot.start_time), minuteTime(slot.end_time)]
  for (const version of availability) {
    if (versions.has(version.version_id) || (version.version_id !== null && (!Number.isSafeInteger(version.version_id) || version.version_id <= 0))) throw new Error('Duplicate or invalid observed grid version')
    const slots = index(version.timeslots, 'version timeslots', organizationId)
    for (const slot of slots.values()) {
      if (!Number.isInteger(slot.day_of_week) || slot.day_of_week < 0 || slot.day_of_week > 6 || minuteTime(slot.start_time) >= minuteTime(slot.end_time)) throw new Error('Invalid observed grid block')
    }
    const preferences = index(version.teachers.map(teacher => ({ ...teacher, id: teacher.teacher_id })), 'availability teachers')
    requireEqual([...preferences.keys()], [...teachers.keys()], 'complete teacher availability')
    for (const teacher of preferences.values()) {
      requireEqual(teacher.entries.map(entry => entry.timeslot_id), [...slots.keys()], 'complete availability grid')
      if (teacher.entries.some(entry => !Number.isInteger(entry.score) || ![-1, 0, 1, 2].includes(entry.score))) throw new Error('Unknown teacher availability score')
    }
    versions.set(version.version_id, { slots, preferences })
  }
  requireEqual([...versions.keys()], [...new Set(days.map(day => day.version_id))], 'observed grid versions')
  const blocked = new Set(), flows = []
  for (const event of index(events, 'calendar events', organizationId).values()) {
    schoolDay(event.start_date)
    schoolDay(event.end_date)
    if (event.start_date > event.end_date || !['national_holiday', 'school_break', 'exam_period', 'other', 'internship_flow'].includes(event.event_type)) throw new Error('Invalid observed calendar event')
    const covered = dates.filter(date => date >= event.start_date && date <= event.end_date)
    if (event.event_type === 'internship_flow') {
      if (!event.class_ids.length || new Set(event.class_ids).size !== event.class_ids.length || event.class_ids.some(id => !classes.has(id))) throw new Error('Internship event references unknown or duplicate classes')
      flows.push({ covered, classes: event.class_ids.map(id => classes.get(id)) })
    } else {
      if (event.class_ids.length) throw new Error('School-wide event has class-specific targets')
      for (const date of covered) blocked.add(date)
    }
  }
  const teachingDates = dates.filter(date => !blocked.has(date) && days.find(day => day.date === date).blocks.length > 0)
  const unavailable = flows.flatMap(flow => flow.covered.filter(date => teachingDates.includes(date)).flatMap(date => flow.classes.map(resource => ({ kind: 'class', resource, date, start: '00:00', end: '23:59' }))))
  const grid = {}
  for (const day of days) {
    const version = versions.get(day.version_id)
    if (!version) throw new Error('Missing observed availability for a grid version')
    const weekday = (schoolDay(day.date).getUTCDay() + 6) % 7
    requireEqual(day.blocks.map(signature), [...version.slots.values()].filter(slot => slot.day_of_week === weekday).map(signature), 'effective daily grid')
    if (!teachingDates.includes(day.date)) continue
    grid[day.date] = day.blocks.map(slot => [minuteTime(slot.start_time), minuteTime(slot.end_time)])
    for (const [teacherId, teacher] of version.preferences) {
      for (const entry of teacher.entries.filter(entry => entry.score === -1)) {
        const slot = day.blocks.find(slot => slot.id === entry.timeslot_id)
        if (slot) unavailable.push({ kind: 'teacher', resource: teachers.get(teacherId), date: day.date, start: minuteTime(slot.start_time), end: minuteTime(slot.end_time) })
      }
    }
  }
  const lunchValues = [gridSettings.lunch_window_start, gridSettings.lunch_window_end, gridSettings.lunch_min_duration_minutes]
  let lunch
  if (lunchValues.some(value => value != null)) {
    if (lunchValues.some(value => value == null) || !Number.isSafeInteger(gridSettings.lunch_min_duration_minutes) || gridSettings.lunch_min_duration_minutes <= 0) throw new Error('Incomplete observed lunch rule')
    lunch = { start: minuteTime(gridSettings.lunch_window_start), end: minuteTime(gridSettings.lunch_window_end), minimum_minutes: gridSettings.lunch_min_duration_minutes }
  }
  return { start_date: year.start_date, hard_end_date: year.hard_end_date, teaching_dates: teachingDates, grid, unavailable, ...(lunch ? { lunch } : {}) }
}

export function canonicalProposalLessons(original, identities, lessons, timezone) {
  const reverse = kind => new Map(Object.entries(identities[kind]).map(([key, id]) => [id, key]))
  const teachers = reverse('teachers'), rooms = reverse('rooms')
  const demands = new Map(original.demand.map(row => [
    `${identities.classes[`${row.course}/${row.class}`]}/${identities.subjects[row.subject]}`,
    [row.course, row.class, row.subject],
  ]))
  const clock = new Intl.DateTimeFormat('en-CA', { timeZone: timezone,
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
  const local = value => {
    if (typeof value !== 'string' || !/T\d{2}:\d{2}:00(?:\.0+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value)) throw new Error('Proposal timestamps must have an explicit timezone and whole minutes')
    const parts = Object.fromEntries(clock.formatToParts(new Date(value)).map(part => [part.type, part.value]))
    return { date: `${parts.year}-${parts.month}-${parts.day}`, time: `${parts.hour}:${parts.minute}` }
  }
  const seen = new Set()
  return lessons.map(lesson => {
    if (!Number.isSafeInteger(lesson.id) || lesson.id <= 0 || seen.has(lesson.id)) throw new Error('Duplicate or invalid proposal lesson identity')
    seen.add(lesson.id)
    const assignment = demands.get(`${lesson.class_id}/${lesson.subject_id}`)
    const teacher = teachers.get(lesson.teacher_id), room = rooms.get(lesson.room_id)
    if (!assignment || !teacher || !room || !Number.isSafeInteger(lesson.assignment_id) || lesson.assignment_id <= 0) throw new Error('Proposal references an unknown original resource')
    const start = local(lesson.starts_at), end = local(lesson.ends_at)
    if (start.date !== lesson.school_date || end.date !== lesson.school_date || !Number.isSafeInteger(lesson.physical_minutes) || lesson.physical_minutes <= 0 || (Date.parse(lesson.ends_at) - Date.parse(lesson.starts_at)) / 60_000 !== lesson.physical_minutes) throw new Error('Proposal date or physical duration differs from its persisted interval')
    const modules = new Map(original.subjects[assignment[2]].modules.map(module => [identities.modules[`${assignment[2]}/${module.code}`], module.code]))
    if (lesson.source_lesson_id != null && (!Number.isSafeInteger(lesson.source_lesson_id) || lesson.source_lesson_id <= 0)) throw new Error('Invalid observed physical origin')
    return { id: lesson.id, assignment, teacher, room, date: lesson.school_date,
      start: start.time, end: end.time, credit_minutes: lesson.credit_minutes,
      ...(lesson.source_lesson_id == null ? {} : { source_id: lesson.source_lesson_id }),
      slices: lesson.slices.map(slice => {
        const module = modules.get(slice.module_id)
        if (!module) throw new Error('Proposal slice references a different subject or unknown original module')
        return { module, offset: slice.offset_minutes, minutes: slice.minutes }
      }) }
  })
}

export function canonicalExecutedModules(original, identities, entries, lessons) {
  const demands = new Map(original.demand.map(row => [`${identities.classes[`${row.course}/${row.class}`]}/${identities.subjects[row.subject]}`, row]))
  const assignments = new Map()
  for (const lesson of lessons) {
    const row = demands.get(`${lesson.class_id}/${lesson.subject_id}`)
    if (!row || !Number.isSafeInteger(lesson.assignment_id) || lesson.assignment_id <= 0 || lesson.teacher_id !== identities.teachers[row.teacher]
      || (assignments.has(lesson.assignment_id) && assignments.get(lesson.assignment_id) !== row)) throw new Error('Observed curricular assignment does not match original resources')
    assignments.set(lesson.assignment_id, row)
  }
  const seen = new Set()
  return entries.map(entry => {
    const row = assignments.get(entry.assignment_id)
    const module = row && original.subjects[row.subject].modules.find(item => identities.modules[`${row.subject}/${item.code}`] === entry.module_id)
    const key = `${entry.assignment_id}/${entry.module_id}`
    if (!row || !module || !Number.isSafeInteger(entry.minutes) || entry.minutes <= 0 || entry.minutes > module.minutes) throw new Error('Unknown or invalid effective module credit')
    if (seen.has(key)) throw new Error('Observed execution contains duplicate module balances')
    seen.add(key)
    return { assignment: [row.course, row.class, row.subject], module: module.code, minutes: entry.minutes }
  })
}

function requireEqual(actual, expected, description) {
  if (!isDeepStrictEqual(sorted(actual), sorted(expected))) throw new Error(`Imported ${description} differ from the original data`)
}

function index(rows, description, organizationId) {
  if (!Array.isArray(rows)) throw new Error(`Missing imported ${description}`)
  const result = new Map()
  for (const row of rows) {
    if (!Number.isSafeInteger(row.id) || row.id <= 0 || result.has(row.id) || (organizationId !== undefined && row.organization_id !== organizationId)) throw new Error(`Invalid imported ${description} identity or tenant`)
    result.set(row.id, row)
  }
  return result
}

export function validateImportedData(original, observed) {
  if (!Number.isSafeInteger(observed.organization_id) || observed.organization_id <= 0) throw new Error('Missing observed school identity')
  const resources = Object.fromEntries(['rooms', 'subjects', 'teachers', 'courses', 'classes'].map(kind => [kind, index(observed[kind], kind, observed.organization_id)]))
  const identities = Object.fromEntries(['rooms', 'subjects', 'modules', 'teachers', 'courses', 'classes', 'assignments'].map(kind => [kind, {}]))
  const identity = (kind, key, id) => {
    if (Object.hasOwn(identities[kind], key)) throw new Error(`Duplicate imported ${kind} reference`)
    identities[kind][key] = id
  }
  requireEqual(observed.rooms.map(row => {
    identity('rooms', row.name, row.id)
    return [row.name, roomType(row.type), row.capacity]
  }), Object.entries(original.rooms).map(([name, row]) => [name, roomType(row.type), row.capacity]), 'rooms')
  const moduleIds = new Set()
  requireEqual(observed.subjects.map(subject => {
    identity('subjects', subject.name, subject.id)
    const modules = [...index(subject.modules, 'modules').values()].map(module => {
      if (module.subject_id !== subject.id || moduleIds.has(module.id)) throw new Error('Imported module has a different subject or duplicate identity')
      moduleIds.add(module.id)
      identity('modules', `${subject.name}/${module.code}`, module.id)
      return [module.name, module.code, module.order + 1, module.hours_total * 60]
    })
    return [subject.name, roomType(subject.required_room_type), sorted(modules)]
  }), Object.entries(original.subjects).map(([name, subject]) => [name, roomType(subject.room_type), sorted(subject.modules.map(module => [module.name, module.code, module.order, module.minutes]))]), 'subjects and modules')
  requireEqual(observed.teachers.map(teacher => {
    identity('teachers', teacher.email, teacher.id)
    return [teacher.email, teacher.name, sorted(teacher.subject_ids.map(id => {
      const subject = resources.subjects.get(id)
      if (!subject) throw new Error('Imported competency references an unknown subject')
      return subject.name
    }))]
  }), Object.entries(original.teachers).map(([email, teacher]) => [email, teacher.name, sorted(teacher.subjects)]), 'teachers and competencies')
  requireEqual(observed.classes.map(schoolClass => {
    const course = resources.courses.get(schoolClass.course_id)
    if (!course) throw new Error('Imported class references an unknown course')
    identity('classes', `${course.abbreviation}/${schoolClass.name}`, schoolClass.id)
    return [course.abbreviation, course.name, schoolClass.name, schoolClass.size, schoolClass.grade_level, schoolClass.start_year, schoolClass.end_year]
  }), original.classes.map(row => [row.course, row.course_name, row.class, row.size, row.grade_level, row.start_year, row.end_year]), 'classes and academic years')
  requireEqual(observed.courses.map(course => {
    identity('courses', course.abbreviation, course.id)
    const classFields = row => [row.id, row.course_id, row.name, row.size, row.grade_level, row.start_year, row.end_year, row.is_archived]
    requireEqual([...index(course.classes, 'course classes', observed.organization_id).values()].map(classFields), observed.classes.filter(row => row.course_id === course.id).map(classFields), 'course class relations')
    return [course.abbreviation, course.name, sorted(course.subjects.map(row => {
      if (resources.subjects.get(row.id)?.name !== row.name) throw new Error('Imported course curriculum references an unknown subject')
      return row.name
    }))]
  }), [...new Map(original.classes.map(row => [row.course, row.course_name]))].map(([abbreviation, name]) => [abbreviation, name, sorted([...new Set(original.demand.filter(row => row.course === abbreviation).map(row => row.subject))])]), 'courses and curricula')
  const seenClasses = new Set(), assignmentIds = new Set(), assignments = []
  for (const group of observed.classSubjects) {
    const schoolClass = resources.classes.get(group.class_id)
    if (!schoolClass || seenClasses.has(group.class_id) || group.grade_level !== schoolClass.grade_level) throw new Error('Invalid imported class assignment group')
    seenClasses.add(group.class_id)
    const course = resources.courses.get(schoolClass.course_id)
    if (group.class_name !== schoolClass.name || group.course_name !== course.name || group.course_abbreviation !== course.abbreviation) throw new Error('Imported class assignment metadata is inconsistent')
    for (const row of index(group.subjects, 'assignments').values()) {
      if (assignmentIds.has(row.id)) throw new Error('Duplicate imported assignment identity across classes')
      assignmentIds.add(row.id)
      const subject = resources.subjects.get(row.subject_id), teacher = resources.teachers.get(row.teacher_id)
      if (!subject || !teacher || row.grade_level !== schoolClass.grade_level || row.subject_name !== subject.name || row.teacher_name !== teacher.name || roomType(row.required_room_type) !== roomType(subject.required_room_type)) throw new Error('Imported assignment has inconsistent references')
      identity('assignments', `${course.abbreviation}/${schoolClass.name}/${subject.name}`, row.id)
      assignments.push({ course: course.abbreviation, class: schoolClass.name, subject: subject.name, teacher: teacher.email, minutes: subject.modules.reduce((sum, module) => sum + module.hours_total * 60, 0) })
    }
  }
  requireEqual([...seenClasses], [...resources.classes.keys()], 'class assignment coverage')
  requireEqual(assignments, original.demand, 'assigned teaching demand')
  for (const [kind, expected] of Object.entries(original.counts)) if (Object.keys(identities[kind]).length !== expected) throw new Error(`Imported ${kind} count differs from originals`)
  return identities
}
