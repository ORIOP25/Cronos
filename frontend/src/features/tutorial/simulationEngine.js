import { TUTORIAL_STEPS } from './contracts'

function createSimulationData() {
  return {
    startDate: '2025-09-15',
    hardEndDate: '2026-07-31',
    slotDuration: 50,
    breakDuration: 10,
    lunchStart: '12:30',
    lunchEnd: '14:30',
    lunchMinDuration: 60,
    sampleCourses: [
      { id: 'demo-course-technology', name: 'Técnico de Informática' },
      { id: 'demo-course-management', name: 'Técnico de Gestão' },
    ],
    sampleTeachers: [
      { id: 'demo-teacher-silva', name: 'Prof. António Silva' },
      { id: 'demo-teacher-santos', name: 'Prof.ª Maria Santos' },
      { id: 'demo-teacher-costa', name: 'Prof. João Costa' },
      { id: 'demo-teacher-martins', name: 'Prof.ª Ana Martins' },
    ],
    sampleClasses: [
      { id: 'demo-class-10a', name: '10º TIS', grade_level: 10, size: 24 },
      { id: 'demo-class-11b', name: '11º TGEI', grade_level: 11, size: 22 },
      { id: 'demo-class-12c', name: '12º TGPSI', grade_level: 12, size: 20 },
    ],
    sampleRooms: [
      { id: 'demo-room-101', name: 'Sala 101', type: 'NORMAL', capacity: 30 },
      { id: 'demo-room-lab2', name: 'Lab 2', type: 'LAB', capacity: 26 },
      { id: 'demo-room-atelier', name: 'Atelier', type: 'ART', capacity: 24 },
    ],
    sampleSubjects: [
      { id: 'demo-subject-prog', name: 'Programação', required_room_type: 'LAB' },
      { id: 'demo-subject-mat', name: 'Matemática', required_room_type: 'NORMAL' },
      { id: 'demo-subject-redes', name: 'Redes', required_room_type: 'LAB' },
      { id: 'demo-subject-gestao', name: 'Gestão', required_room_type: 'NORMAL' },
      { id: 'demo-subject-design', name: 'Design', required_room_type: 'ART' },
    ],
    sampleModules: [
      { id: 'demo-module-prog', subjectId: 'demo-subject-prog', requiredMinutes: 100 },
      { id: 'demo-module-mat', subjectId: 'demo-subject-mat', requiredMinutes: 100 },
      { id: 'demo-module-redes', subjectId: 'demo-subject-redes', requiredMinutes: 100 },
      { id: 'demo-module-gestao', subjectId: 'demo-subject-gestao', requiredMinutes: 100 },
      { id: 'demo-module-design', subjectId: 'demo-subject-design', requiredMinutes: 100 },
    ],
    gridPreview: [
      { day: 'Seg', time: '08:30 - 09:20', subject: 'Programação', room: 'Lab 2', teacher: 'Prof. António Silva' },
      { day: 'Seg', time: '09:30 - 10:20', subject: 'Redes', room: 'Lab 2', teacher: 'Prof. António Silva' },
      { day: 'Ter', time: '10:30 - 11:20', subject: 'Matemática', room: 'Sala 101', teacher: 'Prof.ª Maria Santos' },
      { day: 'Qua', time: '14:30 - 15:20', subject: 'Design', room: 'Atelier', teacher: 'Prof.ª Ana Martins' },
    ],
    workflow: {
      schedulePrepared: true,
      scheduleReviewed: false,
      scheduleApproved: false,
      publishedBlockOpen: false,
      occurrenceCreated: false,
      substitutionCompleted: false,
      debtHours: 2,
      projectedDebtHours: 2,
      repairSimulated: false,
      repairCompared: false,
      historyPreserved: true,
      repairApproved: false,
      lastCheckpoint: null,
    },
  }
}

export function simulationInvariants(data) {
  return {
    courses: data.sampleCourses?.length === 2,
    classes: data.sampleClasses?.length === 3,
    subjects: data.sampleSubjects?.length === 5,
    teachers: data.sampleTeachers?.length === 4,
    rooms: data.sampleRooms?.length === 3,
    modules: data.sampleModules?.length === 5 && data.sampleModules.every((module) => module.requiredMinutes > 0),
    historyPreserved: data.workflow?.historyPreserved === true,
  }
}

function applyStepTransition(data, stepId) {
  const workflow = { ...data.workflow, lastCheckpoint: stepId }
  switch (stepId) {
    case 'schedule_review':
      workflow.scheduleReviewed = workflow.schedulePrepared
      break
    case 'schedule_approve':
      workflow.scheduleApproved = workflow.scheduleReviewed
      break
    case 'published_block_open':
      workflow.publishedBlockOpen = workflow.scheduleReviewed
      break
    case 'occurrence_create':
      workflow.occurrenceCreated = workflow.publishedBlockOpen
      break
    case 'substitution_complete':
      workflow.substitutionCompleted = workflow.occurrenceCreated
      break
    case 'repair_simulate':
      workflow.repairSimulated = true
      workflow.projectedDebtHours = Math.max(0, workflow.debtHours - 1)
      break
    case 'repair_compare':
      workflow.repairCompared = true
      break
    case 'repair_approve':
      workflow.repairApproved = workflow.repairCompared
      break
    default:
      break
  }
  return { ...data, workflow }
}

function createInitialState() {
  return {
    version: 1,
    isOpen: false,
    tutorialRunId: null,
    status: 'NOT_STARTED',
    chapter: 1,
    stepId: TUTORIAL_STEPS[0].id,
    values: {},
    skippedStepIds: [],
    currentStepIndex: 0,
    completed: false,
    skippedSteps: [],
    completedSteps: [],
    simulationData: createSimulationData(),
  }
}

export const INITIAL_SIMULATION_STATE = createInitialState()

export function simulationReducer(state = INITIAL_SIMULATION_STATE, action) {
  if (!action) return state

  switch (action.type) {
    case 'HYDRATE_TUTORIAL':
      return action.payload || state

    case 'OPEN_TUTORIAL': {
      const runId = action.payload?.tutorialRunId || state.tutorialRunId || (
        typeof crypto !== 'undefined' && crypto.randomUUID
          ? crypto.randomUUID()
          : `run-${Date.now()}`
      )
      const shouldResume = action.payload?.resume && state.status === 'IN_PROGRESS'
      return {
        ...state,
        isOpen: true,
        tutorialRunId: runId,
        status: 'IN_PROGRESS',
        currentStepIndex: shouldResume ? state.currentStepIndex : 0,
        stepId: shouldResume ? state.stepId : TUTORIAL_STEPS[0].id,
        chapter: shouldResume ? state.chapter : 1,
        completed: false,
        skippedSteps: shouldResume ? state.skippedSteps : [],
        skippedStepIds: shouldResume ? state.skippedStepIds : [],
        completedSteps: shouldResume ? state.completedSteps : [],
        simulationData: shouldResume ? state.simulationData : createSimulationData(),
      }
    }

    case 'NEXT_STEP': {
      const currentStep = TUTORIAL_STEPS[state.currentStepIndex]
      const nextCompleted = currentStep && !state.completedSteps.includes(currentStep.id)
        ? [...state.completedSteps, currentStep.id]
        : state.completedSteps
      const nextData = applyStepTransition(state.simulationData, currentStep.id)

      if (state.currentStepIndex >= TUTORIAL_STEPS.length - 1) {
        return {
          ...state,
          isOpen: false,
          simulationData: nextData,
          completedSteps: nextCompleted,
          completed: true,
          status: 'COMPLETED',
          stepId: currentStep.id,
          chapter: currentStep.chapter,
        }
      }
      const nextStep = TUTORIAL_STEPS[state.currentStepIndex + 1]
      return {
        ...state,
        simulationData: nextData,
        completedSteps: nextCompleted,
        currentStepIndex: state.currentStepIndex + 1,
        stepId: nextStep.id,
        chapter: nextStep.chapter,
      }
    }

    case 'PREV_STEP': {
      const previousIndex = Math.max(0, state.currentStepIndex - 1)
      return {
        ...state,
        currentStepIndex: previousIndex,
        stepId: TUTORIAL_STEPS[previousIndex].id,
        chapter: TUTORIAL_STEPS[previousIndex].chapter,
      }
    }

    case 'SKIP_STEP': {
      const currentStep = TUTORIAL_STEPS[state.currentStepIndex]
      if (!currentStep?.isSkippable) return state

      const nextSkipped = !state.skippedSteps.includes(currentStep.id)
        ? [...state.skippedSteps, currentStep.id]
        : state.skippedSteps

      if (state.currentStepIndex >= TUTORIAL_STEPS.length - 1) {
        return {
          ...state,
          skippedSteps: nextSkipped,
          skippedStepIds: nextSkipped,
          completed: true,
          status: 'COMPLETED',
          stepId: currentStep.id,
          chapter: currentStep.chapter,
          simulationData: {
            ...state.simulationData,
            workflow: { ...state.simulationData.workflow, lastCheckpoint: currentStep.id },
          },
        }
      }
      const nextStep = TUTORIAL_STEPS[state.currentStepIndex + 1]
      return {
        ...state,
        skippedSteps: nextSkipped,
        skippedStepIds: nextSkipped,
        currentStepIndex: state.currentStepIndex + 1,
        stepId: nextStep.id,
        chapter: nextStep.chapter,
        simulationData: {
          ...state.simulationData,
          workflow: { ...state.simulationData.workflow, lastCheckpoint: currentStep.id },
        },
      }
    }

    case 'JUMP_TO_CHAPTER': {
      const chapterNum = Number(action.payload?.chapter || 1)
      const targetIndex = TUTORIAL_STEPS.findIndex((step) => step.chapter === chapterNum)
      if (targetIndex === -1) return state
      return {
        ...state,
        currentStepIndex: targetIndex,
        stepId: TUTORIAL_STEPS[targetIndex].id,
        chapter: TUTORIAL_STEPS[targetIndex].chapter,
      }
    }

    case 'EXIT_TUTORIAL':
      return { ...state, isOpen: false, status: state.status === 'NOT_STARTED' ? 'IN_PROGRESS' : state.status }

    case 'COMPLETE_TUTORIAL':
      return {
        ...state,
        completed: true,
        status: 'COMPLETED',
        currentStepIndex: TUTORIAL_STEPS.length - 1,
        stepId: TUTORIAL_STEPS[TUTORIAL_STEPS.length - 1].id,
        chapter: 2,
        simulationData: applyStepTransition(state.simulationData, 'repair_approve'),
      }

    case 'SKIP_TUTORIAL':
      return { ...state, isOpen: false, status: 'SKIPPED' }

    case 'REPEAT_TUTORIAL':
      return simulationReducer(state, {
        type: 'OPEN_TUTORIAL',
        payload: { tutorialRunId: action.payload?.tutorialRunId },
      })

    case 'RESET_TUTORIAL':
      return createInitialState()

    case 'UPDATE_SIMULATION_DATA':
      return {
        ...state,
        simulationData: {
          ...state.simulationData,
          ...action.payload,
        },
      }

    default:
      return state
  }
}
