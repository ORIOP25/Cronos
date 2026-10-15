import { useEffect, useMemo } from 'react'
import { toast } from 'react-hot-toast'
import PageHeader from '../components/PageHeader'
import StatePanel from '../components/StatePanel'
import AvailabilityGrid from '../components/AvailabilityGrid'
import AvailabilityToolbar from '../components/AvailabilityToolbar'
import { useCurrentMember } from '../features/members/data'
import { useTimeslots } from '../features/catalog/data'
import { useMyAvailability, useSaveAvailability } from '../features/operations/data'
import { useAttemptScope } from '../hooks/useAttemptScope'
import { useAvailabilityDraft } from '../hooks/useAvailabilityDraft'

const mapAvailabilityApiMessage = (err, context) => {
  const status = err?.response?.status
  if (status === 403) return context === 'load' ? 'Sem permissões para consultar a disponibilidade.' : 'Sem permissões para gravar disponibilidade desta conta.'
  if (status === 404) return 'Perfil de professor não encontrado na organização autenticada.'
  if (status === 400) return 'Dados de disponibilidade inválidos. Atualize a página e tente novamente.'
  return context === 'load' ? 'Falha ao carregar a disponibilidade. Tente novamente.' : 'Erro ao gravar disponibilidade. Tente novamente.'
}

export default function MyAvailability({ readOnly = false, allowedActions, warnOnUnsavedChanges = true }) {
  const { data: currentMember } = useCurrentMember()
  const teacherId = currentMember?.teacher_id
  const timeslotsQuery = useTimeslots()
  const availabilityQuery = useMyAvailability({ enabled: Boolean(teacherId) })
  const saveMutation = useSaveAvailability()
  const attemptScope = useAttemptScope()
  const isTutorial = Array.isArray(allowedActions)
  const canSave = !readOnly && (!isTutorial || allowedActions.includes('UPDATE_AVAILABILITY'))
  const timeslots = useMemo(() => timeslotsQuery.data ?? [], [timeslotsQuery.data])
  const draft = useAvailabilityDraft({
    timeslots,
    rows: availabilityQuery.data,
    disabled: !canSave || saveMutation.isPending,
  })
  const { isDirty } = draft

  useEffect(() => {
    const beforeUnload = (event) => {
      if (!warnOnUnsavedChanges || !isDirty) return
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', beforeUnload)
    return () => window.removeEventListener('beforeunload', beforeUnload)
  }, [isDirty, warnOnUnsavedChanges])

  const handleSave = async () => {
    if (!canSave || !teacherId || !isDirty) return
    const attempt = attemptScope.capture()
    const payload = draft.buildPayload()
    try {
      await saveMutation.mutateAsync({ teacherId, payload })
      if (!attemptScope.isCurrent(attempt)) return
      draft.reset()
      toast.success('Disponibilidade guardada.')
    } catch (error) {
      if (!attemptScope.isCurrent(attempt)) return
      toast.error(mapAvailabilityApiMessage(error, 'save'))
    }
  }

  const queryError = timeslotsQuery.error || availabilityQuery.error
  if (timeslotsQuery.isLoading || availabilityQuery.isLoading) return <><PageHeader preTitle="Professor" title="Minha Disponibilidade" /><StatePanel state="loading" title="A carregar disponibilidade" description="Estamos a preparar a grelha de disponibilidade." /></>
  if (queryError) return <><PageHeader preTitle="Professor" title="Minha Disponibilidade" /><StatePanel state="error" title="Não foi possível carregar a grelha" description={mapAvailabilityApiMessage(queryError, 'load')} action={<button type="button" className="btn btn-outline-primary" onClick={() => { void timeslotsQuery.refetch(); void availabilityQuery.refetch() }}>Tentar novamente</button>} /></>
  if (!timeslots.length) return <><PageHeader preTitle="Professor" title="Minha Disponibilidade" /><StatePanel state="empty" title="A escola ainda não configurou blocos" description="A disponibilidade aparece depois de configurar a grelha horária." /></>

  return (
    <div data-tutorial-target="availability-workspace">
      <PageHeader preTitle="Professor" title="Minha Disponibilidade" description="Escolha uma ferramenta e pinte os blocos. Pode usar rato, toque ou teclado." />
      <AvailabilityToolbar
        selectedScore={draft.selectedScore}
        onSelect={draft.setSelectedScore}
        changedCount={draft.changedCount}
        disabled={!canSave || saveMutation.isPending}
      >
        {isDirty && <button type="button" className="btn btn-link" onClick={draft.reset} disabled={!canSave || saveMutation.isPending}>Repor alterações</button>}
      </AvailabilityToolbar>
      <AvailabilityGrid timeslots={timeslots} availabilityMap={draft.draftMap} onChange={draft.handleGridChange} selectedMode={draft.selectedScore} />
      <div className="d-flex justify-content-end mt-4">
        <button type="button" className="btn btn-primary" onClick={() => { void handleSave() }} disabled={!canSave || !isDirty || saveMutation.isPending}>
          {saveMutation.isPending ? 'A guardar' : 'Guardar disponibilidade'}
        </button>
      </div>
    </div>
  )
}
