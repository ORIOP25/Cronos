import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { resetClerkState, setClerkState } from './setup'
import {
  useCreateMember,
  useCurrentMember,
  useMembers,
  useTeachers,
} from '../features/members/data'
import {
  useAvailableSubjects,
  useClasses,
  useClassSubjects,
  useCourses,
  useCreateSubject,
  useEligibleTeachers,
  useRooms,
  useSubjects,
  useTimeslots,
  useUpdateClassSubjectTeacher,
} from '../features/catalog/data'
import {
  useDebts,
  useOccurrences,
  useTimesheets,
  useUpdateOccurrence,
} from '../features/operations/data'
import {
  useApproveDraft,
  useCancelScheduleTask,
  useCurrentDraftSummary,
  useScheduleDiff,
  useSchedulerStatus,
  useScheduleTaskStatus,
  useTeacherScheduleHorizon,
  useWeekSchedule,
} from '../features/scheduling/data'
import { useCompleteFoundation } from '../features/foundation/foundationData'

vi.mock('../apiClient', () => ({
  default: {
    delete: vi.fn(),
    get: vi.fn(),
    patch: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
  },
}))

import apiClient from '../apiClient'

function createHarness() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  })
  const wrapper = ({ children }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  return { queryClient, wrapper }
}

describe('vertical feature data hooks', () => {
  beforeEach(() => {
    resetClerkState()
    setClerkState({ orgId: 'org-a', isSignedIn: true, isLoaded: true })
    vi.clearAllMocks()
    apiClient.delete.mockResolvedValue(undefined)
    apiClient.get.mockResolvedValue([])
    apiClient.patch.mockResolvedValue({ id: 1 })
    apiClient.post.mockResolvedValue({ id: 1 })
    apiClient.put.mockResolvedValue({ id: 1 })
  })

  it('scopes member reads and invalidations to the active organization', async () => {
    const { queryClient, wrapper } = createHarness()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    const reads = renderHook(() => ({
      current: useCurrentMember(),
      members: useMembers({ includeArchived: true }),
      teachers: useTeachers(),
    }), { wrapper })

    await waitFor(() => expect(reads.result.current.current.isSuccess).toBe(true))
    expect(queryClient.getQueryCache().getAll().map(({ queryKey }) => queryKey)).toEqual(expect.arrayContaining([
      ['current-member', 'org-a'],
      ['members', 'org-a', true],
      ['teachers', 'org-a'],
    ]))
    expect(apiClient.get).toHaveBeenCalledWith('/members', {
      params: { include_archived: true },
    })
    expect(apiClient.get).toHaveBeenCalledWith('/members/me', {
      headers: { Authorization: 'Bearer test_token_123' },
    })

    const mutation = renderHook(() => useCreateMember(), { wrapper })
    await act(() => mutation.result.current.mutateAsync({ name: 'Ana' }))
    expect(invalidate.mock.calls.map(([options]) => options.queryKey)).toEqual(expect.arrayContaining([
      ['members', 'org-a'],
      ['current-member', 'org-a'],
      ['teachers', 'org-a'],
      ['eligible-teachers', 'org-a'],
    ]))
  })

  it('keeps member mutations pending until invalidated queries finish', async () => {
    const { queryClient, wrapper } = createHarness()
    const pendingInvalidations = []
    vi.spyOn(queryClient, 'invalidateQueries').mockImplementation((options) => (
      new Promise((resolve) => pendingInvalidations.push({ options, resolve }))
    ))
    const mutation = renderHook(() => useCreateMember(), { wrapper })

    const mutationPromise = mutation.result.current.mutateAsync({ name: 'Ana' })
    await waitFor(() => expect(pendingInvalidations).toHaveLength(6))
    expect(mutation.result.current.isPending).toBe(true)

    pendingInvalidations.forEach(({ resolve }) => resolve())
    await mutationPromise
    await waitFor(() => expect(mutation.result.current.isPending).toBe(false))
  })

  it('keeps foundation completion pending until all dependent caches reconcile', async () => {
    const { queryClient, wrapper } = createHarness()
    const pendingInvalidations = []
    vi.spyOn(queryClient, 'invalidateQueries').mockImplementation((options) => (
      new Promise((resolve) => pendingInvalidations.push({ options, resolve }))
    ))
    const mutation = renderHook(() => useCompleteFoundation(), { wrapper })

    const mutationPromise = mutation.result.current.mutateAsync({ expected_version: 1, confirmed: true })
    await waitFor(() => expect(pendingInvalidations).toHaveLength(7))
    expect(mutation.result.current.isPending).toBe(true)

    pendingInvalidations.forEach(({ resolve }) => resolve())
    await mutationPromise
    await waitFor(() => expect(mutation.result.current.isPending).toBe(false))
  })

  it('does not execute organization reads without an active organization', async () => {
    setClerkState({ orgId: null })
    const { wrapper } = createHarness()
    renderHook(() => ({
      current: useCurrentMember(),
      courses: useCourses(),
      occurrences: useOccurrences(),
      scheduler: useSchedulerStatus(),
    }), { wrapper })

    await waitFor(() => expect(apiClient.get).not.toHaveBeenCalled())
  })

  it('uses tenant keys and prerequisites for all catalog reads', async () => {
    const { queryClient, wrapper } = createHarness()
    const reads = renderHook(() => ({
      available: useAvailableSubjects(3),
      classes: useClasses(),
      classSubjects: useClassSubjects(3),
      courses: useCourses(),
      eligible: useEligibleTeachers(7),
      rooms: useRooms(),
      subjects: useSubjects(),
      timeslots: useTimeslots(),
    }), { wrapper })

    await waitFor(() => expect(reads.result.current.eligible.isSuccess).toBe(true))
    const keys = queryClient.getQueryCache().getAll().map(({ queryKey }) => queryKey)
    expect(keys).toEqual(expect.arrayContaining([
      ['rooms', 'org-a'],
      ['subjects', 'org-a'],
      ['courses', 'org-a'],
      ['classes', 'org-a'],
      ['timeslots', 'org-a'],
      ['class-subjects', 'org-a', 3],
      ['available-subjects', 'org-a', 3],
      ['eligible-teachers', 'org-a', 7],
    ]))
    expect(apiClient.get).toHaveBeenCalledWith('/rooms/')
    expect(apiClient.get).toHaveBeenCalledWith('/subjects/')
  })

  it('keeps subject-dependent course invalidation inside catalog mutations', async () => {
    const { queryClient, wrapper } = createHarness()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    const mutation = renderHook(() => useCreateSubject(), { wrapper })

    await act(() => mutation.result.current.mutateAsync({ name: 'Matemática' }))

    expect(apiClient.post).toHaveBeenCalledWith('/subjects/', { name: 'Matemática' })
    expect(invalidate.mock.calls.map(([options]) => options.queryKey)).toEqual(expect.arrayContaining([
      ['subjects', 'org-a'],
      ['courses', 'org-a'],
    ]))
  })

  it('refreshes readiness after assigning a teacher to a class subject', async () => {
    const { queryClient, wrapper } = createHarness()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    const mutation = renderHook(() => useUpdateClassSubjectTeacher(), { wrapper })

    await act(() => mutation.result.current.mutateAsync({ classId: 4, subjectId: 7, teacherId: 12 }))

    expect(apiClient.patch).toHaveBeenCalledWith('/classes/4/subjects/7', { teacher_id: 12 })
    expect(invalidate.mock.calls.map(([options]) => options.queryKey)).toEqual(expect.arrayContaining([
      ['dashboard', 'org-a'],
      ['readiness-bases', 'org-a'],
    ]))
  })

  it('passes occurrence, debt, and timesheet filters as Axios params', async () => {
    apiClient.get.mockImplementation((url) => Promise.resolve(url === '/occurrences/' ? [] : []))
    const { wrapper } = createHarness()
    const reads = renderHook(() => ({
      debts: useDebts({ classId: 4 }),
      occurrences: useOccurrences({
        classId: 4,
        dateFrom: '2026-09-01',
        dateTo: '2026-09-30',
        status: 'OPEN',
      }),
      timesheets: useTimesheets('2026-09-07', 'SUBMITTED'),
    }), { wrapper })

    await waitFor(() => expect(reads.result.current.timesheets.isSuccess).toBe(true))
    expect(apiClient.get).toHaveBeenCalledWith('/occurrences/', { params: {
      class_id: 4,
      date_from: '2026-09-01',
      date_to: '2026-09-30',
      status: 'OPEN',
    } })
    expect(apiClient.get).toHaveBeenCalledWith('/occurrences/debts', {
      params: { class_id: 4 },
    })
    expect(apiClient.get).toHaveBeenCalledWith('/timesheets/', { params: {
      week_start_date: '2026-09-07',
      status: 'SUBMITTED',
    } })
  })

  it('invalidates operational tenant roots after an occurrence update', async () => {
    const { queryClient, wrapper } = createHarness()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    const mutation = renderHook(() => useUpdateOccurrence(), { wrapper })

    await act(() => mutation.result.current.mutateAsync({ id: 9, status: 'GAP', version: 2 }))

    expect(invalidate.mock.calls.map(([options]) => options.queryKey)).toEqual(expect.arrayContaining([
      ['occurrences', 'org-a'],
      ['debts', 'org-a'],
      ['weekSchedule', 'org-a'],
      ['classes', 'org-a'],
    ]))
  })

  it('defines scheduling keys, prerequisites, polling, and week params explicitly', async () => {
    apiClient.get.mockImplementation((url) => Promise.resolve(
      url.includes('/scheduler/jobs/') ? { status: 'RUNNING' } : {},
    ))
    const { queryClient, wrapper } = createHarness()
    const reads = renderHook(() => ({
      currentDraft: useCurrentDraftSummary(),
      diff: useScheduleDiff(11),
      horizon: useTeacherScheduleHorizon(),
      job: useScheduleTaskStatus(22),
      status: useSchedulerStatus(),
      week: useWeekSchedule(null, 8, '2026-09-07'),
    }), { wrapper })

    await waitFor(() => expect(reads.result.current.week.isSuccess).toBe(true))
    expect(apiClient.get).toHaveBeenCalledWith('/schedule/week', {
      params: { week_start: '2026-09-07', teacher_id: 8 },
    })
    const jobQuery = queryClient.getQueryCache().find({
      queryKey: ['scheduler-job', 'org-a', 22],
    })
    expect(jobQuery.options.refetchInterval({ state: { data: { status: 'RUNNING' } } })).toBe(5000)
    expect(jobQuery.options.refetchInterval({ state: { data: { status: 'SUCCEEDED' } } })).toBe(false)
    expect(jobQuery.options.refetchInterval({ state: { data: { status: 'STALE' } } })).toBe(false)
  })

  it('owns draft and cancellation invalidation in scheduling mutations', async () => {
    const { queryClient, wrapper } = createHarness()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    const approve = renderHook(() => useApproveDraft(), { wrapper })
    const cancel = renderHook(() => useCancelScheduleTask(), { wrapper })

    await act(() => approve.result.current.mutateAsync({ proposalId: 11 }))
    await act(() => cancel.result.current.mutateAsync(22))

    expect(invalidate.mock.calls.map(([options]) => options.queryKey)).toEqual(expect.arrayContaining([
      ['scheduler-status', 'org-a'],
      ['scheduler-current-draft', 'org-a'],
      ['schedule-diff', 'org-a'],
      ['weekSchedule', 'org-a'],
      ['scheduler-job', 'org-a', 22],
    ]))
  })
})
