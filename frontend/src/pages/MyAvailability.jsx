import { useCallback, useEffect, useMemo, useState } from 'react'
import PageHeader from '../components/PageHeader'
import FeedbackBanner from '../components/FeedbackBanner'
import StatePanel from '../components/StatePanel'
import AvailabilityGrid from '../components/AvailabilityGrid'
import { useCurrentMember } from '../features/members/data'
import { useTimeslots } from '../features/catalog/data'
import { useMyAvailability, useSaveAvailability } from '../features/operations/data'
import { PREFERENCE_LEVELS, DEFAULT_PREFERENCE } from '../constants'

const mapAvailabilityApiMessage = (err, context) => {
  const status = err?.response?.status
  if (status === 403) return context === 'load' ? 'Sem permissões para consultar preferências de disponibilidade.' : 'Sem permissões para gravar disponibilidade desta conta.'
  if (status === 404) return 'Perfil de professor não encontrado na organização autenticada.'
  if (status === 400) return 'Dados de disponibilidade inválidos. Atualize a página e tente novamente.'
  return context === 'load' ? 'Falha ao carregar preferências de disponibilidade. Tente novamente.' : 'Erro ao gravar disponibilidade. Tente novamente.'
}

function toMap(rows = [], validIds) {
  return Object.fromEntries(rows.filter((row) => validIds.has(row.timeslot_id)).map((row) => [row.timeslot_id, Number(row.score)]))
}

export default function MyAvailability({ readOnly = false, allowedActions, warnOnUnsavedChanges = true }) {
  const [draftEdits, setDraftEdits] = useState({})
  const [selectedScore, setSelectedScore] = useState(DEFAULT_PREFERENCE)
  const [feedback, setFeedback] = useState(null)
  const { data: currentMember } = useCurrentMember()
  const teacherId = currentMember?.teacher_id
  const timeslotsQuery = useTimeslots()
  const availabilityQuery = useMyAvailability({ enabled: Boolean(teacherId) })
  const saveMutation = useSaveAvailability()
  const isTutorial = Array.isArray(allowedActions)
  const canSave = !readOnly && (!isTutorial || allowedActions.includes('UPDATE_AVAILABILITY'))
  const timeslots = useMemo(() => timeslotsQuery.data ?? [], [timeslotsQuery.data])
  const persistedMap = useMemo(() => toMap(Array.isArray(availabilityQuery.data) ? availabilityQuery.data : [], new Set(timeslots.map((slot) => slot.id))), [availabilityQuery.data, timeslots])
  const draftMap = useMemo(() => ({ ...persistedMap, ...draftEdits }), [persistedMap, draftEdits])
  const changedIds = useMemo(() => Object.keys(draftEdits).filter((id) => draftEdits[id] !== (persistedMap[id] ?? DEFAULT_PREFERENCE)), [draftEdits, persistedMap])
  const isDirty = changedIds.length > 0

  useEffect(() => {
    const beforeUnload = (event) => {
      if (!warnOnUnsavedChanges || !isDirty) return
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', beforeUnload)
    return () => window.removeEventListener('beforeunload', beforeUnload)
  }, [isDirty, warnOnUnsavedChanges])

  const handleGridChange = useCallback((id, score) => {
    if (!canSave || saveMutation.isPending) return
    setFeedback(null)
    setDraftEdits((current) => {
      const next = { ...current }
      if (score === (persistedMap[id] ?? DEFAULT_PREFERENCE)) delete next[id]
      else next[id] = score
      return next
    })
  }, [canSave, persistedMap, saveMutation.isPending])

  const handleReset = () => { setDraftEdits({}); setFeedback(null) }

  const handleSave = async () => {
    if (!canSave || !teacherId || !isDirty) return
    setFeedback(null)
    const validIds = new Set(timeslots.map((slot) => slot.id))
    const payload = Object.entries(draftMap).filter(([id]) => validIds.has(Number(id))).map(([id, score]) => ({ timeslot_id: Number(id), score }))
    try {
      await saveMutation.mutateAsync({ teacherId, payload })
      setDraftEdits({})
      setFeedback({ tone: 'success', message: 'Preferências guardadas.' })
    } catch (error) {
      setFeedback({ tone: 'danger', message: mapAvailabilityApiMessage(error, 'save') })
    }
  }

  const queryError = timeslotsQuery.error || availabilityQuery.error
  if (timeslotsQuery.isLoading || availabilityQuery.isLoading) return <><PageHeader preTitle="Professor" title="Minhas Preferências" /><StatePanel state="loading" title="A carregar preferências" description="Estamos a preparar a grelha de disponibilidade." /></>
  if (queryError) return <><PageHeader preTitle="Professor" title="Minhas Preferências" /><StatePanel state="error" title="Não foi possível carregar a grelha" description={mapAvailabilityApiMessage(queryError, 'load')} action={<button type="button" className="btn btn-outline-primary" onClick={() => { void timeslotsQuery.refetch(); void availabilityQuery.refetch() }}>Tentar novamente</button>} /></>
  if (!timeslots.length) return <><PageHeader preTitle="Professor" title="Minhas Preferências" /><StatePanel state="empty" title="A escola ainda não configurou blocos" description="As preferências ficam disponíveis depois de a grelha horária ser configurada." /></>

  return (
    <div data-tutorial-target="availability-workspace">
      <PageHeader preTitle="Professor" title="Minhas Preferências" description="Escolha uma ferramenta e pinte os blocos. Pode usar rato, toque ou teclado." />
      {feedback && <div className="mb-3"><FeedbackBanner tone={feedback.tone}>{feedback.message}</FeedbackBanner></div>}
      <div className="availability-toolbar" role="toolbar" aria-label="Ferramentas de disponibilidade">
        <div className="availability-toolbar__tools">
          {[2, 1, 0, -1].map((score) => {
            const info = PREFERENCE_LEVELS[score]
            return <button key={score} type="button" className={`availability-tool${selectedScore === score ? ' is-selected' : ''}`} aria-pressed={selectedScore === score} onClick={() => setSelectedScore(score)} disabled={!canSave || saveMutation.isPending}>
              <span className="availability-tool__swatch" style={{ backgroundColor: info.color }} aria-hidden="true" />{info.label}
            </button>
          })}
        </div>
        <div className="availability-toolbar__status" aria-live="polite">{changedIds.length} {changedIds.length === 1 ? 'bloco alterado' : 'blocos alterados'}</div>
        {isDirty && <button type="button" className="btn btn-link" onClick={handleReset} disabled={!canSave || saveMutation.isPending}>Repor alterações</button>}
      </div>
      <AvailabilityGrid timeslots={timeslots} availabilityMap={draftMap} onChange={handleGridChange} selectedMode={selectedScore} />
      <div className="d-flex justify-content-end mt-4">
        <button type="button" className="btn btn-primary" onClick={() => { void handleSave() }} disabled={!canSave || !isDirty || saveMutation.isPending}>
          {saveMutation.isPending ? 'A guardar' : 'Guardar preferências'}
        </button>
      </div>
    </div>
  )
}
