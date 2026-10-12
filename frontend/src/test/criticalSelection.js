// Authoritative critical CI selection.
// Full mode (default `vitest run`) ignores this file and runs every test under
// src/test. Critical mode (`vitest run --mode critical`) runs only these files.
// Keep this list small and behaviour-critical; the full suite stays optional.

export const criticalNodeTests = [
  'src/test/apiClient.test.js',
  'src/test/apiErrors.test.js',
  'src/test/roleAccess.test.js',
  'src/test/schoolConfigPayloads.test.js',
  'src/test/timeOfDay.test.js',
  'src/test/formatUtils.test.js',
  'src/test/foundationModel.test.js',
  'src/test/securityHeaders.test.js',
  'src/test/e2eClerkSessionReuse.test.js',
]

export const criticalDomTests = [
  'src/test/AppRouteGuards.test.jsx',
  'src/test/useAttemptScope.test.jsx',
  'src/test/UserQueryProvider.test.jsx',
  'src/test/SchedulesSchedulerFlow.test.jsx',
  'src/test/importFiles.test.js',
  'src/test/SmartTable.test.jsx',
  'src/test/ConfirmationModal.test.jsx',
  'src/test/AppToaster.test.jsx',
  'src/test/FeedbackContext.test.jsx',
  'src/test/TimeField.test.jsx',
  'src/test/TurnstileWidget.test.jsx',
  'src/test/networkGuard.test.js',
]

export const criticalNetworkTests = [
  'src/test/featureDataHooks.test.jsx',
  'src/test/schoolConfigData.test.jsx',
]

export const criticalGuardTest = 'src/test/criticalSelection.test.js'

export const criticalTestFiles = [
  ...criticalNodeTests,
  ...criticalDomTests,
  ...criticalNetworkTests,
  criticalGuardTest,
]

// Coverage scope for critical mode. The prior whole-app 45/40/35/45 policy cannot
// hold on a minimal CI run, so the same floors apply to this explicit critical
// source list only. Files the critical tests load but do not own stay in the
// optional full suite coverage.
export const criticalCoverageInclude = [
  'src/apiClient.js',
  'src/utils/apiErrors.js',
  'src/roleAccess.js',
  'src/routeGuards.jsx',
  'src/queryClient.js',
  'src/UserQueryProvider.jsx',
  'src/hooks/useAttemptScope.js',
  'src/utils/formatUtils.js',
  'src/utils/timeOfDay.js',
  'src/utils/schoolConfigPayloads.js',
  'src/features/foundation/foundationModel.js',
  'src/features/foundation/foundationData.js',
  'src/features/imports/data.js',
  'src/features/scheduling/data.js',
  'src/features/members/data.js',
  'src/features/members/recoverOrganizationSession.js',
  'src/features/catalog/data.js',
  'src/features/operations/data.js',
  'src/features/schoolConfig/data.js',
  'src/features/readiness/data.js',
  'src/features/onboarding/useOnboardingCompletion.js',
  'src/components/SmartTable.jsx',
  'src/components/ConfirmationModal.jsx',
  'src/components/AppToaster.jsx',
  'src/components/TimeField.jsx',
  'src/components/FeedbackBanner.jsx',
  'src/components/StatePanel.jsx',
  'src/components/FailureState.jsx',
  'src/features/contact/components/TurnstileWidget.jsx',
  'src/pages/Schedules.jsx',
  'src/App.jsx',
]
