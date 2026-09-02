import apiClient from '../../apiClient'
import { TUTORIAL_VERSION } from './contracts'
import { createTutorialRunId } from './tutorialModel'

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

export async function sendTutorialTelemetryEvent({
  tutorialRunId,
  eventName,
  chapter = null,
  stepId = null,
}) {
  if (!UUID_PATTERN.test(tutorialRunId || '')) return

  const clientEventId =
    typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : createTutorialRunId()

  const payload = {
    tutorial_run_id: tutorialRunId,
    client_event_id: clientEventId,
    tutorial_version: TUTORIAL_VERSION,
    event_name: eventName,
    chapter,
    step_id: stepId,
  }

  try {
    await apiClient.post('/tutorial/telemetry', payload)
  } catch (error) {
    console.error('Tutorial telemetry failed.', error)
  }
}
