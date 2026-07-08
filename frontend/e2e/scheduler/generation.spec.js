import { test, expect } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectRouteReady,
  goTo,
  loginAsAdminReal,
} from '../utils/clerk-helpers.js'

const API_PREFIX = '/api/v1'

async function apiRequest(page, method, path, body) {
  return await page.evaluate(
    async ({ apiPrefix, method: requestMethod, path: requestPath, body: requestBody }) => {
      let token = null
      try {
        token = await window.Clerk?.session?.getToken?.()
      } catch {
        token = null
      }
      if (!token) {
        try {
          const activeSession = window.Clerk?.client?.sessions?.find(
            (session) => session.status === 'active',
          ) || window.Clerk?.client?.sessions?.[0]
          token = await activeSession?.getToken?.()
        } catch {
          token = null
        }
      }
      const headers = {
        'Content-Type': 'application/json',
      }
      if (token) {
        headers.Authorization = `Bearer ${token}`
      }
      const response = await fetch(`${apiPrefix}${requestPath}`, {
        method: requestMethod,
        credentials: 'same-origin',
        headers,
        body: requestBody === undefined ? undefined : JSON.stringify(requestBody),
      })
      const text = await response.text()
      const data = text ? JSON.parse(text) : null
      if (!response.ok) {
        throw new Error(`${requestMethod} ${requestPath} failed: ${response.status} ${text}`)
      }
      return data
    },
    { apiPrefix: API_PREFIX, method, path, body },
  )
}

async function rejectPendingDraftIfPresent(page) {
  const status = await apiRequest(page, 'GET', '/scheduler/status')
  if (status?.pending_draft_id) {
    await apiRequest(page, 'POST', `/scheduler/drafts/${status.pending_draft_id}/reject`)
  }
}

async function findPreparedTeacherMember(page) {
  const teacherEmail = process.env.E2E_CLERK_TEACHER_EMAIL
  if (!teacherEmail) {
    throw new Error('E2E_CLERK_TEACHER_EMAIL is required for scheduler E2E.')
  }

  const members = await apiRequest(page, 'GET', '/members')
  const teacher = members.items.find(
    (member) => member.email.toLowerCase() === teacherEmail.toLowerCase(),
  )
  if (!teacher) {
    throw new Error(`Prepared E2E teacher member not found: ${teacherEmail}`)
  }
  return teacher
}

async function seedMinimalSchedulerInputs(page) {
  await rejectPendingDraftIfPresent(page)

  const unique = Date.now().toString(36)
  const subject = await apiRequest(page, 'POST', '/subjects/', {
    name: `E2E Horario ${unique}`,
    required_room_type: 'normal',
    modules: [
      {
        name: 'Modulo unico',
        code: `M-${unique}`,
        hours_total: 1,
        order: 0,
      },
    ],
  })

  const teacherMember = await findPreparedTeacherMember(page)
  const updatedTeacher = await apiRequest(page, 'PATCH', `/members/${teacherMember.id}`, {
    capabilities: teacherMember.capabilities,
    teacher_access_mode: teacherMember.teacher_access_mode || 'scheduler_only',
    subject_ids: [subject.id],
    lock_version: teacherMember.lock_version,
  })
  if (!updatedTeacher.teacher_id) {
    throw new Error('Prepared E2E teacher did not expose a teacher_id after subject assignment.')
  }

  await apiRequest(page, 'POST', '/school/settings/', {
    school_start_date: '2025-09-15',
    school_hard_end_date: '2026-07-31',
    repair_stability_window_days: 0,
  })
  await apiRequest(page, 'POST', '/school/grid-settings/', {
    lunch_window_start: '12:30',
    lunch_window_end: '14:00',
    lunch_min_duration_minutes: 60,
  })
  await apiRequest(page, 'POST', '/timeslots/generate', {
    start_time: '09:00',
    end_time: '11:00',
    slot_duration_minutes: 60,
    break_duration_minutes: 0,
    days_of_week: [0, 1, 2, 3, 4],
  })
  await apiRequest(page, 'POST', '/rooms/', {
    name: `Sala E2E ${unique}`,
    type: 'normal',
    capacity: 30,
  })
  const course = await apiRequest(page, 'POST', '/courses/', {
    name: `Curso E2E ${unique}`,
    abbreviation: `E${unique.slice(-5)}`.toUpperCase(),
    subject_ids: [],
    teacher_assignments: [],
    classes_config: [],
  })
  const classroom = await apiRequest(page, 'POST', `/courses/${course.id}/classes`, {
    name: `Turma E2E ${unique}`,
    size: 20,
    grade_level: 10,
    start_year: 2025,
    end_year: 2026,
  })
  await apiRequest(page, 'POST', `/classes/${classroom.id}/subjects`, {
    subject_id: subject.id,
  })
  await apiRequest(page, 'PATCH', `/classes/${classroom.id}/subjects/${subject.id}`, {
    teacher_id: updatedTeacher.teacher_id,
  })

  const timeslots = await apiRequest(page, 'GET', '/timeslots/')
  await apiRequest(
    page,
    'POST',
    `/teachers/${updatedTeacher.teacher_id}/availability`,
    timeslots.map((slot) => ({ timeslot_id: slot.id, score: 2 })),
  )

  return { classId: classroom.id, subjectId: subject.id, teacherId: updatedTeacher.teacher_id }
}

async function waitForJobToSucceed(page, jobId) {
  let lastJob = null
  await expect.poll(
    async () => {
      lastJob = await apiRequest(page, 'GET', `/scheduler/jobs/${jobId}`)
      return lastJob.job_status
    },
    {
      message: `scheduler job ${jobId} should finish successfully`,
      intervals: [1000, 2000, 5000],
      timeout: 120_000,
    },
  ).toBe('SUCCEEDED')
  return lastJob
}

test.describe('Scheduler generation', () => {
  test('admin generates a real pending complete draft', async ({ page }) => {
    test.setTimeout(180_000)

    attachRuntimeGuards(page)
    await loginAsAdminReal(page)
    await goTo(page, '/dashboard')
    await seedMinimalSchedulerInputs(page)

    await goTo(page, '/schedules')
    await expectRouteReady(page, '/schedules')
    await expect(page.getByText(/Erro na gera/i)).toHaveCount(0)

    const generateResponse = page.waitForResponse(
      (response) => response.url().includes('/api/v1/scheduler/generate')
        && response.request().method() === 'POST',
    )
    await page.getByRole('button', { name: /Gerar Hor.rio/i }).click()
    const response = await generateResponse
    expect(response.ok()).toBeTruthy()
    const { job_id: jobId } = await response.json()

    const job = await waitForJobToSucceed(page, jobId)
    expect(job.job_status).toBe('SUCCEEDED')

    await expect(page.getByText(/Rascunho pronto para revis/i)).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText('Rascunho pendente').first()).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText('Resultado completo').first()).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText(/Erro na gera/i)).toHaveCount(0)
  })
})
