import apiClient from '../../apiClient'
import { TUTORIAL_VERSION } from './contracts'

export async function sendTutorialTelemetryEvent({
  tutorialRunId,
  eventName,
  chapter = null,
  stepId = null,
}) {
  if (!tutorialRunId) return

  const clientEventId =
    typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : `evt-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`

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
