import { useMemo, useState } from 'react'
import { toast } from 'react-hot-toast'
import { CButton } from '@coreui/react'
import AvailabilityEditorModal from './AvailabilityEditorModal'
import ClassAvailabilityCopyView from './ClassAvailabilityCopyView'
import ConfirmationModal from './ConfirmationModal'
import FeedbackBanner from './FeedbackBanner'
import {
  useClassAvailability,
  useCopyClassAvailability,
  useSaveClassAvailability,
  useTimeslots,
} from '../features/catalog/data'
import { getApiErrorMessage, isApiErrorTransient } from '../utils/apiErrors'

/**
 * Direção edita a disponibilidade semanal de uma turma.
 * A grelha e a cópia partilham a mesma janela do editor de disponibilidade.
 */
export default function ClassAvailabilityModal({ schoolClass, onDate, onClose }) {
  const classId = schoolClass?.id
  const [view, setView] = useState('grid')
  const [selectedIds, setSelectedIds] = useState([])
  const [copyError, setCopyError] = useState('')
  const [confirmVisible, setConfirmVisible] = useState(false)

  const timeslotsQuery = useTimeslots({ onDate })
  const availabilityQuery = useClassAvailability({ classId, onDate })
  const saveMutation = useSaveClassAvailability()
  const copyMutation = useCopyClassAvailability()
  const timeslots = useMemo(() => timeslotsQuery.data ?? [], [timeslotsQuery.data])

  if (!schoolClass) return null

  const openCopyView = () => {
    setSelectedIds([])
    setCopyError('')
    setView('copy')
  }

  const backToGrid = () => {
    setConfirmVisible(false)
    setView('grid')
  }

  const toggleTarget = (id) => setSelectedIds((current) => (
    current.includes(id) ? current.filter((value) => value !== id) : [...current, id]
  ))

  const handleCopy = async () => {
    setCopyError('')
    try {
      const result = await copyMutation.mutateAsync({
        classId,
        targetClassIds: selectedIds,
        ...(onDate ? { onDate } : {}),
      })
      const applied = result?.updated_class_ids?.length ?? selectedIds.length
      setConfirmVisible(false)
      setView('grid')
      toast.success(`Disponibilidade aplicada a ${applied} turmas.`)
    } catch (error) {
      setConfirmVisible(false)
      const message = getApiErrorMessage(error, 'Não foi possível aplicar a disponibilidade.')
      if (isApiErrorTransient(error)) toast.error(message)
      else setCopyError(message)
    }
  }

  const copyBody = view === 'copy' ? (
    <>
      {copyError && <div className="mb-3"><FeedbackBanner tone="danger">{copyError}</FeedbackBanner></div>}
      <ClassAvailabilityCopyView
        originClassId={classId}
        selectedIds={selectedIds}
        onToggle={toggleTarget}
      />
      <ConfirmationModal
        visible={confirmVisible}
        onClose={() => setConfirmVisible(false)}
        onConfirm={() => { void handleCopy() }}
        title="Aplicar disponibilidade"
        message={`Vai substituir a disponibilidade de ${selectedIds.length} turmas pela grelha de ${schoolClass.name}.`}
        confirmText="Aplicar"
        variant="primary"
        isLoading={copyMutation.isPending}
        pendingText="A aplicar…"
      />
    </>
  ) : null

  const copyFooter = view === 'copy' ? (
    <>
      <CButton color="secondary" variant="outline" onClick={backToGrid} disabled={copyMutation.isPending}>
        Voltar
      </CButton>
      <CButton
        color="primary"
        onClick={() => setConfirmVisible(true)}
        disabled={selectedIds.length === 0 || copyMutation.isPending}
      >
        Aplicar a {selectedIds.length} turmas
      </CButton>
    </>
  ) : null

  return (
    <AvailabilityEditorModal
      title={`Disponibilidade — ${schoolClass.name}`}
      intro="Os alunos não usam a aplicação. Esta grelha só afeta os horários gerados a partir de agora."
      onDate={onDate}
      timeslots={timeslots}
      rows={availabilityQuery.data}
      isLoading={timeslotsQuery.isLoading || availabilityQuery.isLoading}
      isError={Boolean(timeslotsQuery.error || availabilityQuery.error)}
      isSaving={saveMutation.isPending}
      successMessage="Disponibilidade da turma guardada."
      onSave={(payload) => saveMutation.mutateAsync({
        classId,
        payload,
        ...(onDate ? { onDate } : {}),
      })}
      onClose={copyMutation.isPending ? undefined : onClose}
      footerStart={({ isDirty }) => (
        <>
          <CButton
            color="secondary"
            variant="outline"
            onClick={openCopyView}
            disabled={isDirty}
            aria-describedby={isDirty ? 'class-availability-copy-hint' : undefined}
          >
            Aplicar a outras turmas…
          </CButton>
          {isDirty && (
            <span id="class-availability-copy-hint" className="small text-muted">
              Guarde primeiro as alterações.
            </span>
          )}
        </>
      )}
      bodyOverride={copyBody}
      footerOverride={copyFooter}
    />
  )
}
