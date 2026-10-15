import { useMemo, useState } from 'react'
import AvailabilityEditorModal from './AvailabilityEditorModal'
import TeacherPresenceSection, {
  arePresenceDraftsEqual,
  presenceDraftFromServer,
  presencePayloadFromDraft,
  validatePresenceDraft,
} from './TeacherPresenceSection'
import { useTimeslots } from '../features/catalog/data'
import {
  useSaveTeacherAvailability,
  useSaveTeacherPresence,
  useTeacherAvailability,
  useTeacherPresence,
} from '../features/operations/data'

const PRESENCE_NOT_SAVED = 'A presença não foi guardada.'
const PRESENCE_SAVED = 'A presença ficou guardada.'

/**
 * Direção edita a disponibilidade de um professor, incluindo quem não tem acesso.
 * A secção "Presença na escola" guarda a regra no seu próprio pedido (T08).
 */
export default function TeacherAvailabilityModal({ teacher, onDate, onClose }) {
  const teacherId = teacher?.id
  const timeslotsQuery = useTimeslots({ onDate })
  const availabilityQuery = useTeacherAvailability({ teacherId, onDate })
  const saveMutation = useSaveTeacherAvailability()
  const presenceQuery = useTeacherPresence({ teacherId })
  const savePresenceMutation = useSaveTeacherPresence()
  const timeslots = useMemo(() => timeslotsQuery.data ?? [], [timeslotsQuery.data])

  // The saved rule is the baseline. Local edits live only in `draftEdits`, so a
  // refetch never overwrites them and a default value never overwrites the
  // stored rule before it loads (R24).
  const serverDraft = useMemo(
    () => (presenceQuery.data ? presenceDraftFromServer(presenceQuery.data) : null),
    [presenceQuery.data],
  )
  const [draftEdits, setDraftEdits] = useState(null)
  const [presenceErrors, setPresenceErrors] = useState({})

  if (!teacher) return null

  const isSaving = saveMutation.isPending || savePresenceMutation.isPending
  const presenceLoaded = serverDraft != null
  const presenceDraft = draftEdits ?? serverDraft
  const presenceDirty = presenceLoaded
    && draftEdits != null
    && !arePresenceDraftsEqual(draftEdits, serverDraft)

  const updatePresence = (nextDraft) => {
    setDraftEdits(nextDraft)
    setPresenceErrors({})
  }

  const savePresence = async () => {
    const errors = validatePresenceDraft(presenceDraft)
    setPresenceErrors(errors)
    if (Object.keys(errors).length > 0) {
      throw new Error(PRESENCE_NOT_SAVED)
    }
    await savePresenceMutation.mutateAsync({
      teacherId,
      payload: presencePayloadFromDraft(presenceDraft),
    })
  }

  const resetPresence = () => {
    setPresenceErrors({})
    setDraftEdits(null)
  }

  return (
    <AvailabilityEditorModal
      title={`Disponibilidade — ${teacher.name}`}
      intro="Esta edição é administrativa. Não envia convite nem altera o acesso do professor."
      onDate={onDate}
      timeslots={timeslots}
      rows={availabilityQuery.data}
      isLoading={timeslotsQuery.isLoading || availabilityQuery.isLoading}
      isError={Boolean(timeslotsQuery.error || availabilityQuery.error)}
      isSaving={isSaving}
      successMessage="Disponibilidade guardada. Recomendações atualizadas."
      saveLabel="Guardar disponibilidade"
      beforeGrid={(
        <TeacherPresenceSection
          draft={presenceDraft}
          fieldErrors={presenceErrors}
          onChange={updatePresence}
          disabled={!presenceLoaded || presenceQuery.isError || isSaving}
          isLoading={presenceQuery.isLoading}
          isError={presenceQuery.isError}
          onRetry={() => { void presenceQuery.refetch() }}
        />
      )}
      extraPart={presenceLoaded ? {
        isDirty: presenceDirty,
        save: savePresence,
        reset: resetPresence,
        failureMessage: PRESENCE_NOT_SAVED,
        savedMessage: PRESENCE_SAVED,
      } : undefined}
      onSave={(payload) => saveMutation.mutateAsync({
        teacherId,
        payload,
        ...(onDate ? { onDate } : {}),
      })}
      onClose={onClose}
    />
  )
}
