import { useMemo, useState } from 'react'
import { DEFAULT_PREFERENCE } from '../constants'

/**
 * Local draft of availability edits over the persisted rows, plus the active paint tool.
 * `disabled` freezes edits (read-only or while saving).
 */
export function useAvailabilityDraft({ timeslots, rows, disabled }) {
  const [draftEdits, setDraftEdits] = useState({})
  const [selectedScore, setSelectedScore] = useState(DEFAULT_PREFERENCE)
  const validIds = useMemo(() => new Set(timeslots.map((slot) => slot.id)), [timeslots])
  const persistedMap = useMemo(
    () => Object.fromEntries(
      (Array.isArray(rows) ? rows : [])
        .filter((row) => validIds.has(row.timeslot_id))
        .map((row) => [row.timeslot_id, Number(row.score)])
    ),
    [rows, validIds]
  )
  const draftMap = useMemo(() => ({ ...persistedMap, ...draftEdits }), [persistedMap, draftEdits])
  const changedCount = useMemo(
    () => Object.keys(draftEdits).filter((id) => draftEdits[id] !== (persistedMap[id] ?? DEFAULT_PREFERENCE)).length,
    [draftEdits, persistedMap]
  )

  const handleGridChange = (id, score) => {
    if (disabled) return
    setDraftEdits((current) => {
      const next = { ...current }
      if (score === (persistedMap[id] ?? DEFAULT_PREFERENCE)) delete next[id]
      else next[id] = score
      return next
    })
  }

  const buildPayload = () => Object.entries(draftMap)
    .filter(([id]) => validIds.has(Number(id)))
    .map(([id, score]) => ({ timeslot_id: Number(id), score }))

  return {
    draftMap,
    changedCount,
    isDirty: changedCount > 0,
    selectedScore,
    setSelectedScore,
    handleGridChange,
    reset: () => setDraftEdits({}),
    buildPayload,
  }
}
