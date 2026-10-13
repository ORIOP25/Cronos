import { runIdentityCampaign } from '../utils/ui-identity-campaign.js'
import { test } from './fixtures.js'

test('founder verifies delivered email and recovers a credential through the UI', {
  annotation: ['E2E-01/founder-registration', 'E2E-01/email-verification', 'E2E-01/foundation-completion', 'E2E-02/admin-login-logout', 'E2E-02/new-context-login', 'E2E-03/delivered-recovery', 'E2E-03/recovered-login', 'E2E-05/five-original-imports', 'E2E-05/import-report', 'E2E-07/ten-foundation-steps', 'E2E-07/preferred-date-draft', 'E2E-07/calendar-persistence']
    .concat(['E2E-05/entity-relations', 'E2E-05/reload-persistence', 'E2E-04/delivered-invitation', 'E2E-04/invitation-acceptance', 'E2E-04/pending-conversion-relations', 'E2E-02/teacher-login-logout'])
    .concat(['E2E-15/teacher-admin-routes-denied', 'E2E-15/denied-actions-no-effects', 'E2E-16/five-model-downloads', 'E2E-16/authenticated-404'])
    .concat(['E2E-06/availability-persistence', 'E2E-06/archive-restore'])
    .concat(['E2E-06/resource-crud', 'E2E-06/initial-class'])
    .concat(['E2E-07/readiness', 'E2E-08/generation-confirmation', 'E2E-08/terminal-job'])
    .concat(['E2E-08/complete-coverage', 'E2E-08/hard-constraints'])
    .concat(['E2E-09/approve-proposal', 'E2E-09/teacher-published-schedule', 'E2E-09/new-session-progress'])
    .concat(['E2E-09/reject-proposal'])
    .concat(['E2E-10/premature-execution-blocked', 'E2E-12/incomplete-week-blocked'])
    .concat(['E2E-17/guide-complete-resume', 'E2E-17/tutorial-isolation'])
    .concat(['E2E-03/credential-change'])
    .concat(['E2E-18/school-year-change', 'E2E-18/disposable-school-deletion', 'E2E-18/protected-history'])
    .concat(['E2E-14/distinct-schools', 'E2E-14/switch-without-cache-leak', 'E2E-14/stale-feedback-blocked'])
    .concat(['E2E-11/pending-zero-credit', 'E2E-11/gap-debt'])
    .concat(['E2E-11/planned-substitution-reservation'])
    .concat(['E2E-11/stale-version'])
    .map(description => ({ type: 'acceptance-case', description })),
}, async ({ page, browser, provenance, deliveredMail, registerSecret, runtime }, testInfo) => {
  await runIdentityCampaign({ page, browser, provenance, deliveredMail, registerSecret, runtime }, testInfo)
})
