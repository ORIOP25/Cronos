import { existsSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { criticalCoverageInclude, criticalTestFiles } from './criticalSelection.js'

const frontendRoot = resolve(import.meta.dirname, '../..')

// Observable snapshot of the critical selection. Update it deliberately when the
// selection changes; this is the guard that fails on a silently removed or
// unexpected critical test. Not a source/regex scrape.
const EXPECTED_CRITICAL_SELECTION = [
  'src/test/AppRouteGuards.test.jsx',
  'src/test/AppToaster.test.jsx',
  'src/test/ConfirmationModal.test.jsx',
  'src/test/FeedbackContext.test.jsx',
  'src/test/SchedulesSchedulerFlow.test.jsx',
  'src/test/SmartTable.test.jsx',
  'src/test/TimeField.test.jsx',
  'src/test/TurnstileWidget.test.jsx',
  'src/test/UserQueryProvider.test.jsx',
  'src/test/apiClient.test.js',
  'src/test/apiErrors.test.js',
  'src/test/criticalSelection.test.js',
  'src/test/e2eClerkSessionReuse.test.js',
  'src/test/featureDataHooks.test.jsx',
  'src/test/formatUtils.test.js',
  'src/test/foundationModel.test.js',
  'src/test/importFiles.test.js',
  'src/test/networkGuard.test.js',
  'src/test/roleAccess.test.js',
  'src/test/schoolConfigData.test.jsx',
  'src/test/schoolConfigPayloads.test.js',
  'src/test/securityHeaders.test.js',
  'src/test/timeOfDay.test.js',
  'src/test/useAttemptScope.test.jsx',
]

// Critical source modules that the selected tests own or exercise. This is a
// functionality selection, never pruned to keep a coverage number green.
const EXPECTED_CRITICAL_SOURCES = [
  'src/App.jsx',
  'src/apiClient.js',
  'src/components/AppToaster.jsx',
  'src/components/ConfirmationModal.jsx',
  'src/components/FailureState.jsx',
  'src/components/FeedbackBanner.jsx',
  'src/components/SmartTable.jsx',
  'src/components/StatePanel.jsx',
  'src/components/TimeField.jsx',
  'src/features/contact/components/TurnstileWidget.jsx',
  'src/features/catalog/data.js',
  'src/features/foundation/foundationData.js',
  'src/features/foundation/foundationModel.js',
  'src/features/imports/data.js',
  'src/features/members/data.js',
  'src/features/members/recoverOrganizationSession.js',
  'src/features/onboarding/useOnboardingCompletion.js',
  'src/features/operations/data.js',
  'src/features/readiness/data.js',
  'src/features/scheduling/data.js',
  'src/features/schoolConfig/data.js',
  'src/hooks/useAttemptScope.js',
  'src/pages/Schedules.jsx',
  'src/queryClient.js',
  'src/roleAccess.js',
  'src/routeGuards.jsx',
  'src/utils/apiErrors.js',
  'src/utils/formatUtils.js',
  'src/utils/schoolConfigPayloads.js',
  'src/utils/timeOfDay.js',
  'src/UserQueryProvider.jsx',
]

function localTestCorpus() {
  return readdirSync(resolve(frontendRoot, 'src/test'))
    .filter((name) => /\.test\.jsx?$/.test(name))
    .map((name) => `src/test/${name}`)
}

describe('critical CI selection', () => {
  it('is not empty', () => {
    expect(criticalTestFiles.length).toBeGreaterThan(0)
  })

  it('selects only unique test files under src/test', () => {
    expect(new Set(criticalTestFiles).size).toBe(criticalTestFiles.length)
    for (const file of criticalTestFiles) {
      expect(file, file).toMatch(/^src\/test\/.+\.test\.jsx?$/)
    }
  })

  it('every selected critical test exists locally', () => {
    for (const file of criticalTestFiles) {
      expect(existsSync(resolve(frontendRoot, file)), file).toBe(true)
    }
  })

  it('selects a strict subset of the local test corpus', () => {
    const corpus = localTestCorpus()
    for (const file of criticalTestFiles) {
      expect(corpus, file).toContain(file)
    }
  })

  it('matches the observable critical test snapshot', () => {
    expect([...criticalTestFiles].sort()).toEqual([...EXPECTED_CRITICAL_SELECTION].sort())
  })

  it('keeps the critical source scope explicit', () => {
    expect(criticalCoverageInclude.length).toBeGreaterThan(0)
    expect(new Set(criticalCoverageInclude).size).toBe(criticalCoverageInclude.length)
    for (const file of criticalCoverageInclude) {
      expect(existsSync(resolve(frontendRoot, file)), file).toBe(true)
      expect(file, file).toMatch(/^src\/.+\.jsx?$/)
    }
  })

  it('keeps every selected owned source in the coverage scope', () => {
    for (const file of EXPECTED_CRITICAL_SOURCES) {
      expect(criticalCoverageInclude, file).toContain(file)
    }
  })

  it('matches the observable critical source snapshot', () => {
    expect([...criticalCoverageInclude].sort()).toEqual([...EXPECTED_CRITICAL_SOURCES].sort())
  })
})
