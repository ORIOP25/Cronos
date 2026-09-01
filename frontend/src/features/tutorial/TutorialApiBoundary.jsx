import { useEffect, useMemo } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { ApiClientProvider } from '../../ApiClientContext'
import { createQueryClient } from '../../queryClient'
import { createApiClient } from '../../apiClient'
import { createTutorialApiAdapter } from './tutorialApiAdapter'
import { applyTutorialDemoAction } from './tutorialScenario'

function createScenarioRuntime(initialScenario) {
  let currentScenario = initialScenario
  return {
    getScenario: () => currentScenario,
    applyAction: (action) => {
      currentScenario = applyTutorialDemoAction(currentScenario, action)
      return currentScenario
    },
  }
}

export function TutorialApiBoundary({ stepId, readOnly = false, scenario, children }) {
  const queryClient = useMemo(() => createQueryClient('tutorial-demo'), [])
  const runtime = useMemo(() => {
    const runtimeValue = createScenarioRuntime(scenario)
    return {
      ...runtimeValue,
      client: createApiClient({
        authenticate: false,
        adapter: createTutorialApiAdapter({
          stepId,
          readOnly,
          getScenario: runtimeValue.getScenario,
          applyAction: runtimeValue.applyAction,
        }),
      }),
    }
  }, [readOnly, scenario, stepId])

  useEffect(() => () => queryClient.clear(), [queryClient])

  return (
    <ApiClientProvider client={runtime.client}>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </ApiClientProvider>
  )
}
