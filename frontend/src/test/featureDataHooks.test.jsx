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
  useClassAvailability,
  useClasses,
  useClassSubjects,
  useCopyClassAvailability,
  useCourses,
  useCreateJointGroup,
  useCreateSubject,
  useDeleteJointGroup,
  useEligibleTeachers,
  useJointCandidates,
  useRooms,
  useSaveClassAvailability,
  useSubjects,
  useTimeslots,
  useUpdateClassSubject,
  useUpdateCourseClass,
  useUpdateJointGroup,
  useWeekGridVersions,
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
    await waitFor(() => expect(pendingInvalidations).toHaveLength(8))
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
    await waitFor(() => expect(pendingInvalidations).toHaveLength(9))
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

  it('loads per-day grid versions for the selected week', async () => {
    const rangePayload = {
      days: [{ date: '2026-09-21', version_id: 1, effective_date: '2025-09-15', blocks: [] }],
      transition_date: null,
    }
    apiClient.get.mockImplementation((url) => Promise.resolve(
      url === '/timeslots/range' ? rangePayload : [],
    ))
    const { queryClient, wrapper } = createHarness()
    const read = renderHook(() => useWeekGridVersions('2026-09-21'), { wrapper })

    await waitFor(() => expect(read.result.current.isSuccess).toBe(true))
    expect(apiClient.get).toHaveBeenCalledWith('/timeslots/range', {
      params: { from_date: '2026-09-21', to_date: '2026-09-27' },
    })
    expect(read.result.current.data).toEqual(rangePayload)
    expect(queryClient.getQueryCache().getAll().map(({ queryKey }) => queryKey))
      .toContainEqual(['timeslots', 'org-a', 'range', '2026-09-21'])
  })

  it('does not request grid versions without a week', async () => {
    const { wrapper } = createHarness()
    renderHook(() => useWeekGridVersions(''), { wrapper })

    await waitFor(() => expect(apiClient.get).not.toHaveBeenCalled())
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

  it('updates a class through its course and refreshes tenant catalog queries', async () => {
    const { queryClient, wrapper } = createHarness()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    const mutation = renderHook(() => useUpdateCourseClass(), { wrapper })
    const data = { name: '10.º B', size: 25 }

    await act(() => mutation.result.current.mutateAsync({ courseId: 7, classId: 11, data }))

    expect(apiClient.patch).toHaveBeenCalledWith('/courses/7/classes/11', data)
    expect(invalidate.mock.calls.map(([options]) => options.queryKey)).toEqual(expect.arrayContaining([
      ['courses', 'org-a'],
      ['classes', 'org-a'],
      ['readiness-bases', 'org-a'],
    ]))
  })

  it('reads, saves, and copies class availability with tenant keys and invalidations', async () => {
    const { queryClient, wrapper } = createHarness()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    const read = renderHook(() => useClassAvailability({ classId: 9, onDate: '2031-01-01' }), { wrapper })

    await waitFor(() => expect(read.result.current.isSuccess).toBe(true))
    expect(apiClient.get).toHaveBeenCalledWith('/classes/9/availability', {
      params: { on_date: '2031-01-01' },
    })
    expect(queryClient.getQueryCache().getAll().map(({ queryKey }) => queryKey))
      .toContainEqual(['class-availability', 'org-a', 9, '2031-01-01'])
    read.unmount()

    const save = renderHook(() => useSaveClassAvailability(), { wrapper })
    const payload = [{ timeslot_id: 11, score: 0 }]
    await act(() => save.result.current.mutateAsync({
      classId: 9, payload, onDate: '2031-01-01',
    }))
    expect(apiClient.put).toHaveBeenCalledWith('/classes/9/availability', payload, {
      params: { on_date: '2031-01-01' },
    })
    expect(queryClient.getQueryData(['class-availability', 'org-a', 9, '2031-01-01'])).toEqual(payload)
    expect(invalidate.mock.calls.map(([options]) => options.queryKey)).toEqual(expect.arrayContaining([
      ['class-availability', 'org-a'],
      ['dashboard', 'org-a'],
      ['readiness-bases', 'org-a'],
      ['scheduler-prevalidation', 'org-a'],
    ]))

    invalidate.mockClear()
    const copy = renderHook(() => useCopyClassAvailability(), { wrapper })
    await act(() => copy.result.current.mutateAsync({
      classId: 9, targetClassIds: [3, 4], onDate: '2031-01-01',
    }))
    expect(apiClient.post).toHaveBeenCalledWith('/classes/9/availability/copy', {
      target_class_ids: [3, 4],
    }, { params: { on_date: '2031-01-01' } })
    expect(invalidate.mock.calls.map(([options]) => options.queryKey)).toEqual(expect.arrayContaining([
      ['class-availability', 'org-a'],
      ['readiness-bases', 'org-a'],
    ]))
  })

  it('sends only the provided class-subject fields and preserves teacher_id null', async () => {
    const { queryClient, wrapper } = createHarness()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    const mutation = renderHook(() => useUpdateClassSubject(), { wrapper })

    await act(() => mutation.result.current.mutateAsync({ classId: 4, subjectId: 7, teacherId: null }))
    await act(() => mutation.result.current.mutateAsync({ classId: 4, subjectId: 7, moduleIds: [3, 1] }))

    expect(apiClient.patch).toHaveBeenCalledWith('/classes/4/subjects/7', { teacher_id: null })
    expect(apiClient.patch).toHaveBeenCalledWith('/classes/4/subjects/7', { module_ids: [3, 1] })
    expect(invalidate.mock.calls.map(([options]) => options.queryKey)).toEqual(expect.arrayContaining([
      ['classes', 'org-a'],
      ['teacher-progress', 'org-a'],
      ['dashboard', 'org-a'],
      ['readiness-bases', 'org-a'],
    ]))
  })

  it('sends only the defined fields and refreshes the class, teacher progress, and preparation queries', async () => {
    const { queryClient, wrapper } = createHarness()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    const setQueryData = vi.spyOn(queryClient, 'setQueryData')
    const response = { id: 7, subject_id: 7, modules: [{ id: 1, selected: false }] }
    apiClient.patch.mockResolvedValue(response)
    const mutation = renderHook(() => useUpdateClassSubject(), { wrapper })

    await act(() => mutation.result.current.mutateAsync({ classId: 4, subjectId: 7, moduleIds: [2, 3] }))

    expect(apiClient.patch).toHaveBeenCalledWith('/classes/4/subjects/7', { module_ids: [2, 3] })
    expect(setQueryData).toHaveBeenCalledWith(['class-subjects', 'org-a', 4], response)
    expect(invalidate.mock.calls.map(([options]) => options.queryKey)).toEqual(expect.arrayContaining([
      ['classes', 'org-a'],
      ['teacher-progress', 'org-a'],
      ['dashboard', 'org-a'],
      ['readiness-bases', 'org-a'],
    ]))
  })

  it('invalidates the other joint member class caches after a teacher update', async () => {
    const { queryClient, wrapper } = createHarness()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    const response = {
      class_name: '10.º A',
      subjects: [
        { subject_id: 7, joint_group: { id: 3, classes: [{ class_id: 11 }, { class_id: 12 }] } },
      ],
    }
    apiClient.patch.mockResolvedValue(response)
    queryClient.setQueryData(['class-subjects', 'org-a', 11], { subjects: [] })
    queryClient.setQueryData(['class-subjects', 'org-a', 12], { subjects: [] })
    const mutation = renderHook(() => useUpdateClassSubject(), { wrapper })

    await act(() => mutation.result.current.mutateAsync({ classId: 11, subjectId: 7, teacherId: 9 }))

    expect(apiClient.patch).toHaveBeenCalledWith('/classes/11/subjects/7', { teacher_id: 9 })
    expect(queryClient.getQueryData(['class-subjects', 'org-a', 11])).toEqual(response)
    expect(invalidate.mock.calls.map(([options]) => options.queryKey)).toEqual(expect.arrayContaining([
      ['class-subjects', 'org-a', 12],
      ['joint-candidates', 'org-a'],
      ['classes', 'org-a'],
      ['teacher-progress', 'org-a'],
      ['readiness-bases', 'org-a'],
    ]))
  })

  it('loads the joint candidates for the selected subject and class', async () => {
    apiClient.get.mockResolvedValue([
      { class_id: 5, selected_module_ids: [1, 2], started_module_ids: [1] },
    ])
    const { queryClient, wrapper } = createHarness()
    const read = renderHook(() => useJointCandidates(7, 4), { wrapper })

    await waitFor(() => expect(read.result.current.isSuccess).toBe(true))
    expect(apiClient.get).toHaveBeenCalledWith('/subjects/7/joint-candidates', {
      params: { class_id: 4 },
    })
    expect(queryClient.getQueryCache().getAll().map(({ queryKey }) => queryKey))
      .toContainEqual(['joint-candidates', 'org-a', 7, 4, null])
  })

  it('loads the current joint group members with the optional group id', async () => {
    apiClient.get.mockResolvedValue([
      { class_id: 4, name: '10.º A', selected_module_ids: [1], started_module_ids: [] },
    ])
    const { queryClient, wrapper } = createHarness()
    const read = renderHook(() => useJointCandidates(7, 4, 9), { wrapper })

    await waitFor(() => expect(read.result.current.isSuccess).toBe(true))
    expect(apiClient.get).toHaveBeenCalledWith('/subjects/7/joint-candidates', {
      params: { class_id: 4, group_id: 9 },
    })
    expect(queryClient.getQueryCache().getAll().map(({ queryKey }) => queryKey))
      .toContainEqual(['joint-candidates', 'org-a', 7, 4, 9])
  })

  it('requests the source class facts when include_source is set', async () => {
    apiClient.get.mockResolvedValue([
      { class_id: 4, name: '10.º A', selected_module_ids: [1], started_module_ids: [1] },
    ])
    const { queryClient, wrapper } = createHarness()
    const read = renderHook(() => useJointCandidates(7, 4, null, true), { wrapper })

    await waitFor(() => expect(read.result.current.isSuccess).toBe(true))
    expect(apiClient.get).toHaveBeenCalledWith('/subjects/7/joint-candidates', {
      params: { class_id: 4, include_source: true },
    })
    expect(queryClient.getQueryCache().getAll().map(({ queryKey }) => queryKey))
      .toContainEqual(['joint-candidates', 'org-a', 7, 4, null, 'include_source'])
  })

  it('invalidates every member class after creating a joint group', async () => {
    const { queryClient, wrapper } = createHarness()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    apiClient.post.mockResolvedValue({ id: 9 })
    const mutation = renderHook(() => useCreateJointGroup(), { wrapper })

    await act(() => mutation.result.current.mutateAsync({
      subjectId: 7,
      classIds: [4, 5],
      moduleIds: [1, 2],
      teacherId: 3,
    }))

    expect(apiClient.post).toHaveBeenCalledWith('/joint-lesson-groups', {
      subject_id: 7,
      class_ids: [4, 5],
      module_ids: [1, 2],
      teacher_id: 3,
    })
    expect(invalidate.mock.calls.map(([options]) => options.queryKey)).toEqual(expect.arrayContaining([
      ['class-subjects', 'org-a', 4],
      ['class-subjects', 'org-a', 5],
      ['classes', 'org-a'],
      ['readiness-bases', 'org-a'],
      ['joint-candidates', 'org-a'],
    ]))
  })

  it('invalidates new and old member classes after updating a joint group', async () => {
    const { queryClient, wrapper } = createHarness()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    apiClient.put.mockResolvedValue({ id: 9 })
    const mutation = renderHook(() => useUpdateJointGroup(), { wrapper })

    await act(() => mutation.result.current.mutateAsync({
      groupId: 9,
      classIds: [5, 6],
      previousClassIds: [4],
      moduleIds: [1],
      teacherId: 3,
    }))

    expect(apiClient.put).toHaveBeenCalledWith('/joint-lesson-groups/9', {
      class_ids: [5, 6],
      module_ids: [1],
      teacher_id: 3,
    })
    expect(invalidate.mock.calls.map(([options]) => options.queryKey)).toEqual(expect.arrayContaining([
      ['class-subjects', 'org-a', 5],
      ['class-subjects', 'org-a', 6],
      ['class-subjects', 'org-a', 4],
      ['classes', 'org-a'],
      ['joint-candidates', 'org-a'],
    ]))
  })

  it('invalidates the former member classes after deleting a joint group', async () => {
    const { queryClient, wrapper } = createHarness()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    apiClient.delete.mockResolvedValue(undefined)
    const mutation = renderHook(() => useDeleteJointGroup(), { wrapper })

    await act(() => mutation.result.current.mutateAsync({ groupId: 9, classIds: [4, 5] }))

    expect(apiClient.delete).toHaveBeenCalledWith('/joint-lesson-groups/9')
    expect(invalidate.mock.calls.map(([options]) => options.queryKey)).toEqual(expect.arrayContaining([
      ['class-subjects', 'org-a', 4],
      ['class-subjects', 'org-a', 5],
      ['classes', 'org-a'],
      ['readiness-bases', 'org-a'],
      ['joint-candidates', 'org-a'],
    ]))
  })

  it('sends class_ids when deciding a joint occurrence', async () => {
    const { wrapper } = createHarness()
    const mutation = renderHook(() => useUpdateOccurrence(), { wrapper })

    await act(() => mutation.result.current.mutateAsync({
      id: 9,
      status: 'GAP',
      version: 2,
      classIds: [4, 5],
    }))

    expect(apiClient.patch).toHaveBeenCalledWith('/occurrences/9', {
      status: 'GAP',
      version: 2,
      substitute_teacher_id: null,
      substitute_subject_id: null,
      class_ids: [4, 5],
    })
  })

  it('caches the updated class-subjects response after a module change', async () => {
    const { queryClient, wrapper } = createHarness()
    const payload = { class_id: 4, class_name: 'TEE', subjects: [] }
    apiClient.patch.mockResolvedValue(payload)
    const mutation = renderHook(() => useUpdateClassSubject(), { wrapper })

    await act(() => mutation.result.current.mutateAsync({ classId: 4, subjectId: 7, moduleIds: [] }))

    expect(queryClient.getQueryData(['class-subjects', 'org-a', 4])).toEqual(payload)
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
