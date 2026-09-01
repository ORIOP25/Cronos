import { describe, expect, it } from 'vitest'
import { TUTORIAL_ACTIONS } from '../features/tutorial/tutorialContent'
import { applyTutorialDemoAction, createTutorialScenario } from '../features/tutorial/tutorialScenario'
import { createTutorialApiAdapter } from '../features/tutorial/tutorialApiAdapter'

function makeRuntime(stepId, readOnly = false) {
  let scenario = createTutorialScenario(stepId)
  const adapter = createTutorialApiAdapter({
    stepId,
    readOnly,
    getScenario: () => scenario,
    applyAction: (action) => {
      scenario = applyTutorialDemoAction(scenario, action)
      return scenario
    },
  })
  return {
    request: (url, config = {}) => adapter({ url, ...config }),
    getScenario: () => scenario,
  }
}

describe('tutorial v3 local API adapter', () => {
  it('serves the deterministic catalog and class plan through the normal API shapes', async () => {
    const runtime = makeRuntime('class_plan')
    const subjects = (await runtime.request('/subjects/')).data
    expect(subjects).toHaveLength(2)
    expect(subjects[0]).toMatchObject({ id: 1, name: 'Programação', required_room_type: 'lab' })
    expect(subjects[0].modules[0]).toMatchObject({ hours_total: 2 })

    const course = (await runtime.request('/courses/1')).data
    expect(course).toMatchObject({ id: 1, name: 'Curso de Informática', abbreviation: 'TIS' })
    expect(course.classes).toEqual([expect.objectContaining({ id: 1, name: '10.º TIS', course_id: 1 })])

    const classSubjects = (await runtime.request('/classes/1/subjects')).data
    expect(classSubjects.subjects).toEqual(expect.arrayContaining([
      expect.objectContaining({ subject_id: 1, teacher_id: 1 }),
    ]))
    expect((await runtime.request('/classes/1/available-subjects')).data).toEqual([])
    expect((await runtime.request('/classes/subjects/1/eligible-teachers')).data).toEqual([
      expect.objectContaining({ id: 1, subject_ids: [1] }),
    ])
  })

  it('applies a declared catalog mutation in-memory before returning its response', async () => {
    const runtime = makeRuntime('rooms')
    const response = await runtime.request('/rooms/1', {
      method: 'patch',
      data: JSON.stringify({ name: 'Laboratório atualizado', type: 'lab', capacity: 30 }),
    })
    expect(response.status).toBe(200)
    expect(response.data).toMatchObject({ name: 'Laboratório atualizado', capacity: 30 })
    expect((await runtime.request('/rooms/')).data[0]).toMatchObject({ name: 'Laboratório atualizado', capacity: 30 })
  })

  it('supports availability writes with the same array payload as the live page', async () => {
    const runtime = makeRuntime('availability')
    const response = await runtime.request('/teachers/me/availability', {
      method: 'put',
      data: JSON.stringify([{ timeslot_id: 1, score: -1 }, { timeslot_id: 2, score: 2 }]),
    })
    expect(response.data).toEqual(expect.arrayContaining([
      { timeslot_id: 1, score: -1 },
      { timeslot_id: 2, score: 2 },
    ]))
    expect((await runtime.request('/teachers/me/availability')).data[0]).toEqual({ timeslot_id: 1, score: -1 })
  })

  it('supports complete schedule generation and approval without network requests', async () => {
    const runtime = makeRuntime('schedule')
    expect((await runtime.request('/scheduler/status')).data).toMatchObject({ pending_draft_id: null, can_generate_new_draft: true })
    const generated = await runtime.request('/scheduler/generate', { method: 'post', data: '{}' })
    expect(generated.data).toMatchObject({ job_id: 81, status: 'SUCCEEDED' })
    expect((await runtime.request('/scheduler/drafts/current')).data).toMatchObject({
      draft_id: 71,
      result_category: 'COMPLETE_SUCCESS',
    })
    expect((await runtime.request('/scheduler/drafts/71/diff')).data[0]).toMatchObject({ change_type: 'MOVED' })
    const approved = await runtime.request('/scheduler/drafts/71/approve', { method: 'post' })
    expect(approved.data).toMatchObject({ draft_id: 71, draft_state: 'APPROVED' })
    expect((await runtime.request('/scheduler/drafts/current')).data).toBeNull()
  })

  it('starts recovery with a pending partial draft and only publishes it on approval', async () => {
    const runtime = makeRuntime('recovery')
    expect((await runtime.request('/scheduler/drafts/current')).data).toMatchObject({
      draft_id: 72,
      result_category: 'PARTIAL_RECOVERY',
      debt_hours_before: 2,
      debt_hours_recovered: 1,
      debt_hours_remaining: 1,
    })
    const response = await runtime.request('/scheduler/drafts/72/approve', { method: 'post' })
    expect(response.data).toMatchObject({ draft_id: 72, draft_state: 'APPROVED' })
    expect((await runtime.request('/scheduler/drafts/current')).data).toBeNull()
    expect(runtime.getScenario().publishedRecoveryBlockIds).toEqual(['demo-block-recovery-1'])

    const baseWeek = (await runtime.request('/schedule/week', { params: { week_start: '2025-09-15' } })).data
    expect(baseWeek.some((slot) => slot.is_draft)).toBe(false)

    const recoveryWeek = (await runtime.request('/schedule/week', { params: { week_start: '2025-09-22' } })).data
    expect(recoveryWeek).toEqual([
      expect.objectContaining({
        date: '2025-09-23',
        is_draft: false,
        timeslot: expect.objectContaining({ day_of_week: 1 }),
      }),
    ])
  })

  it('creates an occurrence and then decides the prepared substitution', async () => {
    const occurrenceRuntime = makeRuntime('occurrences')
    await occurrenceRuntime.request('/schedule/active-blocks/1/log', {
      method: 'put',
      data: JSON.stringify({ status: 'OCCURRENCE', summary: '', notes: '' }),
    })
    expect((await occurrenceRuntime.request('/occurrences')).data.items[0]).toMatchObject({
      operational_state: 'OPEN_PENDING',
      status: 'GAP',
    })

    const substitutionRuntime = makeRuntime('substitutions')
    expect((await substitutionRuntime.request('/occurrences/1/substitutes/recommendations')).data[0]).toMatchObject({
      teacher_id: 2,
      subject_id: 2,
    })
    const decided = await substitutionRuntime.request('/occurrences/1', {
      method: 'patch',
      data: JSON.stringify({ status: 'SUBSTITUTED', substitute_teacher_id: 2, substitute_subject_id: 2 }),
    })
    expect(decided.data).toMatchObject({ operational_state: 'DECIDED_SUBSTITUTED', substitute_teacher_id: 2 })
  })

  it('returns the fixed debts and read-only operational pages', async () => {
    const debts = makeRuntime('hour_debts')
    expect((await debts.request('/occurrences/debts')).data).toMatchObject({
      total_gaps: 2,
      total_hours_owed: 2,
    })
    expect((await debts.request('/timesheets')).data[0]).toMatchObject({ total_slots: 2, occurrence_slots: 1 })

    const readOnly = makeRuntime('recovery', true)
    await expect(readOnly.request('/scheduler/drafts/72/approve', { method: 'post' })).rejects.toMatchObject({
      response: { status: 403, data: { detail: { code: 'DEMO_READ_ONLY' } } },
    })

    const weeklyClose = makeRuntime('weekly_close')
    expect((await weeklyClose.request('/timesheets', { params: { week_start_date: '2025-09-15' } })).data[0]).toMatchObject({
      week_start_date: '2025-09-15',
      week_end_date: '2025-09-21',
      status: 'SUBMITTED',
    })
    expect((await weeklyClose.request('/schedule/week', { params: { week_start: '2025-09-15', teacher_id: 1 } })).data)
      .toEqual(expect.arrayContaining([expect.objectContaining({ week_timesheet_status: 'SUBMITTED' })]))
  })

  it('rejects routes and actions outside the current step contract', async () => {
    const runtime = makeRuntime('weekly_close')
    await expect(runtime.request('/scheduler/generate', { method: 'post' })).rejects.toMatchObject({
      response: { status: 403, data: { detail: { code: 'DEMO_ACTION_NOT_ALLOWED' } } },
    })
    await expect(runtime.request('/not-a-tutorial-route')).rejects.toMatchObject({
      response: { status: 400, data: { detail: { code: 'TUTORIAL_ROUTE_NOT_DECLARED' } } },
    })
    await expect(runtime.request('/scheduler/drafts/71/diff')).rejects.toMatchObject({
      response: { status: 404, data: { detail: { code: 'DRAFT_NOT_FOUND' } } },
    })
    await expect(runtime.request('/scheduler/jobs/999')).rejects.toMatchObject({
      response: { status: 404, data: { detail: { code: 'JOB_NOT_FOUND' } } },
    })
    expect(TUTORIAL_ACTIONS.GENERATE_SCHEDULE).toBe('GENERATE_SCHEDULE')
  })

  it('validates the substitution decision before resolving substitute entities', async () => {
    const runtime = makeRuntime('substitutions')
    await expect(runtime.request('/occurrences/1', {
      method: 'patch',
      data: JSON.stringify({ status: 'GAP' }),
    })).rejects.toMatchObject({
      response: { status: 400, data: { detail: { message: expect.stringContaining('SUBSTITUTED') } } },
    })
  })
})
