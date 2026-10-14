import { useMemo } from 'react'
import AvailabilityEditorModal from './AvailabilityEditorModal'
import { useTimeslots } from '../features/catalog/data'
import { useSaveTeacherAvailability, useTeacherAvailability } from '../features/operations/data'

/**
 * Direção edita a disponibilidade de um professor, incluindo quem não tem acesso.
 */
export default function TeacherAvailabilityModal({ teacher, onDate, onClose }) {
  const timeslotsQuery = useTimeslots({ onDate })
  const availabilityQuery = useTeacherAvailability({ teacherId: teacher?.id, onDate })
  const saveMutation = useSaveTeacherAvailability()
  const timeslots = useMemo(() => timeslotsQuery.data ?? [], [timeslotsQuery.data])

  if (!teacher) return null

  return (
    <AvailabilityEditorModal
      title={`Disponibilidade — ${teacher.name}`}
      intro="Esta edição é administrativa. Não envia convite nem altera o acesso do professor."
      onDate={onDate}
      timeslots={timeslots}
      rows={availabilityQuery.data}
      isLoading={timeslotsQuery.isLoading || availabilityQuery.isLoading}
      isError={Boolean(timeslotsQuery.error || availabilityQuery.error)}
      isSaving={saveMutation.isPending}
      successMessage="Disponibilidade guardada. Recomendações atualizadas."
      saveLabel="Guardar disponibilidade"
      onSave={(payload) => saveMutation.mutateAsync({
        teacherId: teacher.id,
        payload,
        ...(onDate ? { onDate } : {}),
      })}
      onClose={onClose}
    />
  )
}
