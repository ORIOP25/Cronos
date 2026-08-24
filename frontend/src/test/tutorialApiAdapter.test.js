import { describe, expect, it, vi } from 'vitest'
import { INITIAL_TUTORIAL_STATE } from '../features/tutorial/tutorialModel'
import { createTutorialScenario } from '../features/tutorial/tutorialScenario'
import { createTutorialApiAdapter } from '../features/tutorial/tutorialApiAdapter'

describe('tutorial API adapter', () => {
  it('accepts the array payload used by the availability checkpoint', async () => {
    const onDomainMutation = vi.fn()
    const scenario = createTutorialScenario({
      ...INITIAL_TUTORIAL_STATE,
      stepId: 'availability_review',
      status: 'IN_PROGRESS',
    })
    const adapter = createTutorialApiAdapter({
      getScenario: () => scenario,
      onDomainMutation,
    })
    const payload = [{ timeslot_id: 1, score: -1 }]

    const result = await adapter({
      url: '/teachers/me/availability',
      method: 'put',
      data: JSON.stringify(payload),
    })

    expect(result.status).toBe(200)
    expect(onDomainMutation).toHaveBeenCalledWith(expect.objectContaining({
      method: 'put',
      path: '/teachers/me/availability',
      body: payload,
    }))
  })
})
