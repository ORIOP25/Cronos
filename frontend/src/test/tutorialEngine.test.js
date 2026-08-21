import { describe, expect, it } from 'vitest'
import {
  TUTORIAL_STEPS,
  TUTORIAL_VERSION,
  getTutorialStorageKey,
} from '../features/tutorial/contracts'
import {
  simulationReducer,
  INITIAL_SIMULATION_STATE,
  simulationInvariants,
} from '../features/tutorial/simulationEngine'

describe('tutorialEngine', () => {
  it('has exactly 24 canonical steps across 2 chapters with TUTORIAL_VERSION = 1', () => {
    expect(TUTORIAL_VERSION).toBe(1)
    expect(TUTORIAL_STEPS).toHaveLength(24)

    const chapters = new Set(TUTORIAL_STEPS.map((s) => s.chapter))
    expect(chapters).toEqual(new Set([1, 2]))

    const c1Steps = TUTORIAL_STEPS.filter((s) => s.chapter === 1)
    const c2Steps = TUTORIAL_STEPS.filter((s) => s.chapter === 2)
    expect(c1Steps).toHaveLength(14)
    expect(c2Steps).toHaveLength(10)

    // Check step ids are unique
    const ids = TUTORIAL_STEPS.map((s) => s.id)
    expect(ids).toEqual([
      'structure_overview',
      'subject_create',
      'module_add',
      'course_create',
      'class_create',
      'teacher_add',
      'teacher_competency',
      'room_add',
      'assignment_create',
      'availability_review',
      'schedule_prepare',
      'schedule_review',
      'schedule_approve',
      'chapter_transition',
      'published_block_open',
      'occurrence_create',
      'substitute_teacher_select',
      'substitute_subject_select',
      'substitution_complete',
      'debt_observe',
      'repair_simulate',
      'repair_compare',
      'history_verify',
      'repair_approve',
    ])
    expect(new Set(ids).size).toBe(24)
  })

  it('proves exactly 7 unskippable and 17 skippable steps (2^17 = 131072 combinations)', () => {
    const unskippableSteps = TUTORIAL_STEPS.filter((s) => !s.isSkippable)
    const skippableSteps = TUTORIAL_STEPS.filter((s) => s.isSkippable)

    expect(unskippableSteps).toHaveLength(7)
    expect(skippableSteps).toHaveLength(17)

    const combinations = 2 ** skippableSteps.length
    expect(combinations).toBe(131072)
  })

  it('generates the canonical isolated storage key format', () => {
    const key1 = getTutorialStorageKey('user_123', 'org_abc')
    expect(key1).toBe('cronos:tutorial:v1:user:user_123:org:org_abc')

    const keyDefault = getTutorialStorageKey(null, null)
    expect(keyDefault).toBe('cronos:tutorial:v1:user:anonymous:org:personal')
  })

  it('transitions state correctly on open, next, prev, skip, and exit', () => {
    // 1. OPEN_TUTORIAL
    let state = simulationReducer(INITIAL_SIMULATION_STATE, {
      type: 'OPEN_TUTORIAL',
      payload: { tutorialRunId: 'run-uuid-123' },
    })
    expect(state.isOpen).toBe(true)
    expect(state.tutorialRunId).toBe('run-uuid-123')
    expect(state.currentStepIndex).toBe(0)
    expect(state.completed).toBe(false)

    // Step 1 is unskippable
    expect(TUTORIAL_STEPS[0].isSkippable).toBe(false)
    const afterAttemptSkip = simulationReducer(state, { type: 'SKIP_STEP' })
    expect(afterAttemptSkip.currentStepIndex).toBe(0)
    expect(afterAttemptSkip.skippedSteps).toHaveLength(0)

    // 2. NEXT_STEP advances to step 2
    state = simulationReducer(state, { type: 'NEXT_STEP' })
    expect(state.currentStepIndex).toBe(1)
    expect(state.completedSteps).toContain(TUTORIAL_STEPS[0].id)

    // 3. PREV_STEP returns to step 1
    state = simulationReducer(state, { type: 'PREV_STEP' })
    expect(state.currentStepIndex).toBe(0)

    // 4. NEXT_STEP to step 2 (which is skippable)
    state = simulationReducer(state, { type: 'NEXT_STEP' })
    expect(state.currentStepIndex).toBe(1)
    expect(TUTORIAL_STEPS[1].isSkippable).toBe(true)

    // SKIP_STEP on step 2
    state = simulationReducer(state, { type: 'SKIP_STEP' })
    expect(state.currentStepIndex).toBe(2)
    expect(state.skippedSteps).toContain(TUTORIAL_STEPS[1].id)
    expect(simulationInvariants(state.simulationData)).toEqual({
      courses: true,
      classes: true,
      subjects: true,
      teachers: true,
      rooms: true,
      modules: true,
      historyPreserved: true,
    })

    // 5. EXIT_TUTORIAL
    state = simulationReducer(state, { type: 'EXIT_TUTORIAL' })
    expect(state.isOpen).toBe(false)
  })

  it(
    'exhaustively simulates all 131,072 (2^17) skip combinations deterministically',
    () => {
      const TOTAL_COMBINATIONS = 1 << 17 // 131072
      const baseOpenState = simulationReducer(INITIAL_SIMULATION_STATE, {
        type: 'OPEN_TUTORIAL',
        payload: { tutorialRunId: 'test-run-benchmark' },
      })

      const skipAction = { type: 'SKIP_STEP' }
      const nextAction = { type: 'NEXT_STEP' }

      for (let mask = 0; mask < TOTAL_COMBINATIONS; mask++) {
        let state = baseOpenState
        let skippablePointer = 0
        let expectedSkipCount = 0

        for (let stepIdx = 0; stepIdx < 24; stepIdx++) {
          const step = TUTORIAL_STEPS[stepIdx]
          if (step.isSkippable) {
            const shouldSkip = (mask & (1 << skippablePointer)) !== 0
            skippablePointer++
            if (shouldSkip) {
              expectedSkipCount++
              state = simulationReducer(state, skipAction)
            } else {
              state = simulationReducer(state, nextAction)
            }
          } else {
            state = simulationReducer(state, nextAction)
          }
        }

        expect(state.completed).toBe(true)
        expect(state.skippedSteps.length).toBe(expectedSkipCount)
        expect(Object.values(simulationInvariants(state.simulationData)).every(Boolean)).toBe(true)
      }
    },
    30000,
  )
})
