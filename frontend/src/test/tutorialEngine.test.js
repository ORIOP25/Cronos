import { describe, expect, it, vi } from 'vitest'
import {
  TUTORIAL_ACTIONS,
  TUTORIAL_CHAPTERS,
  TUTORIAL_COPY,
  TUTORIAL_STEPS,
  TUTORIAL_VERSION,
  getTutorialStorageKey,
} from '../features/tutorial/tutorialContent'
import {
  INITIAL_TUTORIAL_STATE,
  applyTutorialTransition,
  getTutorialProgressPercent,
  validateTutorialState,
} from '../features/tutorial/tutorialModel'
import {
  applyTutorialDemoAction,
  createTutorialScenario,
  tutorialScenarioInvariants,
} from '../features/tutorial/tutorialScenario'

describe('tutorial v3 domain', () => {
  it('requires secure randomness when a tutorial run starts', () => {
    vi.stubGlobal('crypto', {})
    try {
      expect(() => applyTutorialTransition(INITIAL_TUTORIAL_STATE, { type: 'START' })).toThrow()
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('declares the 13 feature steps in two chapters', () => {
    expect(TUTORIAL_VERSION).toBe(3)
    expect(TUTORIAL_STEPS).toHaveLength(13)
    expect(TUTORIAL_STEPS.slice(0, 7).every((step) => step.chapter === 1)).toBe(true)
    expect(TUTORIAL_STEPS.slice(7).every((step) => step.chapter === 2)).toBe(true)
    expect(new Set(TUTORIAL_STEPS.map((step) => step.id)).size).toBe(13)
    expect(TUTORIAL_STEPS.map((step) => step.id)).toEqual([
      'curriculum', 'courses_classes', 'team', 'rooms', 'class_plan',
      'availability', 'schedule', 'occurrences', 'substitutions',
      'weekly_close', 'hour_debts', 'recovery', 'history',
    ])
    expect(TUTORIAL_CHAPTERS).toHaveLength(2)
    expect(TUTORIAL_STEPS.every((step) => step.page && step.target && step.allowedActions)).toBe(true)
    expect(TUTORIAL_STEPS.find((step) => step.id === 'availability').description).toBe(
      'Antes de distribuir as aulas, conhecemos a disponibilidade dos professores. '
      + 'Cada bloco fica Preferencial, Neutro, Evitar ou Impossível.',
    )
  })

  it('keeps the guide copy and persistence key tenant-specific', () => {
    expect(TUTORIAL_COPY.ribbon).toBe('Ambiente de demonstração · os dados da escola não são alterados.')
    expect(getTutorialStorageKey('user_123', 'org_abc')).toBe('cronos:tutorial:v3:user:user_123:org:org_abc')
    expect(getTutorialStorageKey(null, null)).toBeNull()
  })

  it('creates a pure deterministic scenario for every step', () => {
    for (const step of TUTORIAL_STEPS) {
      const scenario = createTutorialScenario(step.id)
      const invariants = tutorialScenarioInvariants(scenario)
      expect(Object.values(invariants).every(Boolean)).toBe(true)
      expect(scenario.stepId).toBe(step.id)
      expect(scenario.weekStart).toBe('2025-09-15')
      expect(scenario.referenceDate).toBe('2025-09-20T12:00:00Z')
      expect(scenario.slotDurationMinutes).toBe(60)
      expect([...scenario.courses, ...scenario.classes, ...scenario.subjects, ...scenario.modules,
        ...scenario.teachers, ...scenario.rooms, ...scenario.classSubjects, ...scenario.timeslots,
        ...scenario.blocks].every((item) => item.id.startsWith('demo-'))).toBe(true)
    }
  })

  it('keeps the debt and recovery example deterministic', () => {
    const scenario = createTutorialScenario('recovery')
    expect(scenario.debt).toMatchObject({
      hoursOwedMinutes: 120,
      proposedRecoveryMinutes: 60,
      remainingMinutes: 60,
    })
    expect(scenario.draft).toMatchObject({
      kind: 'RECOVERY',
      resultCategory: 'PARTIAL_RECOVERY',
      debtHoursBefore: 2,
      debtHoursRecovered: 1,
      debtHoursRemaining: 1,
    })
  })

  it('applies declared demo actions without mutating the source scenario', () => {
    const subjectScenario = createTutorialScenario('curriculum')
    const editedSubject = applyTutorialDemoAction(subjectScenario, {
      type: TUTORIAL_ACTIONS.UPDATE_SUBJECT,
      subjectId: 1,
      data: {
        name: 'Programação Aplicada',
        room_type_id: 2,
        modules: [{ name: 'Algoritmos', code: 'UFCD-A', hours_total: 2 }],
      },
    })
    expect(subjectScenario.subjects[0].name).toBe('Programação')
    expect(editedSubject.subjects[0].name).toBe('Programação Aplicada')
    expect(editedSubject.modules).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: 'demo-module-edited-1', requiredMinutes: 120 }),
    ]))

    const classScenario = createTutorialScenario('courses_classes')
    const editedClass = applyTutorialDemoAction(classScenario, {
      type: TUTORIAL_ACTIONS.UPDATE_CLASS,
      courseId: 1,
      classId: 1,
      data: { name: '10.º TIS', grade_level: 10, size: 24, start_year: 2025, end_year: 2028 },
    })
    expect(editedClass.classes[0]).toMatchObject({ name: '10.º TIS', size: 24 })

    const memberScenario = createTutorialScenario('team')
    const editedMember = applyTutorialDemoAction(memberScenario, {
      type: TUTORIAL_ACTIONS.UPDATE_MEMBER_COMPETENCIES,
      memberId: 1,
      data: { subject_ids: [1, 2] },
    })
    expect(editedMember.teachers[0].competencies).toHaveLength(2)

    const roomScenario = createTutorialScenario('rooms')
    const editedRoom = applyTutorialDemoAction(roomScenario, {
      type: TUTORIAL_ACTIONS.UPDATE_ROOM,
      roomId: 1,
      data: { name: 'Laboratório maior', room_type_id: 2, capacity: 30 },
    })
    expect(editedRoom.rooms[0]).toMatchObject({ name: 'Laboratório maior', capacity: 30 })

    const planScenario = createTutorialScenario('class_plan')
    const editedAssignment = applyTutorialDemoAction(planScenario, {
      type: TUTORIAL_ACTIONS.UPDATE_CLASS_SUBJECT_TEACHER,
      classId: 1,
      subjectId: 1,
      teacherId: 1,
    })
    expect(editedAssignment.classSubjects[0].teacherId).toBe('demo-teacher-programming')

    const availabilityScenario = createTutorialScenario('availability')
    const editedAvailability = applyTutorialDemoAction(availabilityScenario, {
      type: TUTORIAL_ACTIONS.UPDATE_AVAILABILITY,
      slots: [{ timeslot_id: 1, score: -1 }],
    })
    expect(editedAvailability.availability.slots[0].score).toBe(-1)
    expect(availabilityScenario.availability.slots[0].score).toBe(1)
  })

  it('accepts school-defined room type ids in the demo scenario', () => {
    const subjectScenario = createTutorialScenario('curriculum')
    const editedSubject = applyTutorialDemoAction(subjectScenario, {
      type: TUTORIAL_ACTIONS.UPDATE_SUBJECT,
      subjectId: 1,
      data: { room_type_id: 5 },
    })
    const roomScenario = createTutorialScenario('rooms')
    const editedRoom = applyTutorialDemoAction(roomScenario, {
      type: TUTORIAL_ACTIONS.UPDATE_ROOM,
      roomId: 1,
      data: { name: 'Oficina 2', room_type_id: 5, capacity: 30 },
    })

    expect(editedSubject.subjects[0].roomType).toBe('OFICINA')
    expect(editedRoom.rooms[0].type).toBe('OFICINA')
  })

  it('models schedule, occurrence, substitution and recovery actions', () => {
    const schedule = createTutorialScenario('schedule')
    const generated = applyTutorialDemoAction(schedule, { type: TUTORIAL_ACTIONS.GENERATE_SCHEDULE })
    expect(generated.draft).toMatchObject({ kind: 'SCHEDULE', resultCategory: 'COMPLETE_SUCCESS' })
    const approved = applyTutorialDemoAction(generated, { type: TUTORIAL_ACTIONS.APPROVE_SCHEDULE, draftId: 71 })
    expect(approved.draft).toBeNull()

    const occurrenceScenario = createTutorialScenario('occurrences')
    const withOccurrence = applyTutorialDemoAction(occurrenceScenario, {
      type: TUTORIAL_ACTIONS.CREATE_OCCURRENCE,
      blockId: 1,
      status: 'OCCURRENCE',
    })
    expect(withOccurrence.occurrences).toHaveLength(1)

    const substitutionScenario = createTutorialScenario('substitutions')
    const substituted = applyTutorialDemoAction(substitutionScenario, {
      type: TUTORIAL_ACTIONS.DECIDE_SUBSTITUTION,
      occurrenceId: 1,
      status: 'SUBSTITUTED',
      substituteTeacherId: 2,
      substituteSubjectId: 2,
    })
    expect(substituted.occurrences[0]).toMatchObject({
      status: 'SUBSTITUTED',
      operationalState: 'DECIDED_SUBSTITUTED',
    })

    const recovery = createTutorialScenario('recovery')
    const recoveryApproved = applyTutorialDemoAction(recovery, {
      type: TUTORIAL_ACTIONS.APPROVE_RECOVERY,
      draftId: 72,
    })
    expect(recoveryApproved.draft).toBeNull()
    expect(recoveryApproved.publishedRecoveryBlockIds).toContain('demo-block-recovery-1')
  })

  it('advances only with an exact expected step and ignores duplicate clicks', () => {
    const started = applyTutorialTransition(INITIAL_TUTORIAL_STATE, { type: 'START', tutorialRunId: 'run-v3' })
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(applyTutorialTransition(started, { type: 'ADVANCE', expectedStepId: 'courses_classes' })).toBe(started)
    expect(consoleError).toHaveBeenCalled()
    consoleError.mockRestore()

    const advanced = applyTutorialTransition(started, { type: 'ADVANCE', expectedStepId: 'curriculum' })
    expect(advanced).toEqual({ version: 3, tutorialRunId: 'run-v3', status: 'IN_PROGRESS', stepId: 'courses_classes' })
    expect(applyTutorialTransition(advanced, { type: 'ADVANCE', expectedStepId: 'curriculum' })).toBe(advanced)
  })

  it('keeps progress derived from the current feature index', () => {
    let state = applyTutorialTransition(INITIAL_TUTORIAL_STATE, { type: 'START', tutorialRunId: 'run-progress' })
    expect(getTutorialProgressPercent(state)).toBe(0)
    for (let index = 0; index < TUTORIAL_STEPS.length - 1; index += 1) {
      state = applyTutorialTransition(state, { type: 'ADVANCE', expectedStepId: TUTORIAL_STEPS[index].id })
    }
    expect(state.stepId).toBe(TUTORIAL_STEPS.at(-1).id)
    expect(getTutorialProgressPercent(state)).toBeLessThan(100)
    state = applyTutorialTransition(state, { type: 'ADVANCE', expectedStepId: TUTORIAL_STEPS.at(-1).id })
    expect(state.status).toBe('COMPLETED')
    expect(getTutorialProgressPercent(state)).toBe(100)
  })

  it('supports integral skip, exit, repeat and rejects extra persisted fields', () => {
    const started = applyTutorialTransition(INITIAL_TUTORIAL_STATE, { type: 'START', tutorialRunId: 'run-skip' })
    const skipped = applyTutorialTransition(started, { type: 'SKIP_TUTORIAL' })
    expect(skipped).toMatchObject({ status: 'SKIPPED', stepId: 'curriculum', tutorialRunId: 'run-skip' })
    expect(applyTutorialTransition(skipped, { type: 'EXIT' })).toBe(skipped)

    const repeated = applyTutorialTransition(skipped, { type: 'REPEAT', tutorialRunId: 'run-repeat' })
    expect(repeated).toEqual({ version: 3, tutorialRunId: 'run-repeat', status: 'IN_PROGRESS', stepId: 'curriculum' })
    expect(validateTutorialState({ ...repeated, chapter: 1 }).valid).toBe(false)
  })
})
