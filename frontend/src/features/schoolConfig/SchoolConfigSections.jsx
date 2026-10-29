import { useState } from 'react'
import { toast } from 'react-hot-toast'
import {
  CCard, CCardBody, CCardHeader, CCol, CRow, CForm, CFormInput,
  CFormCheck, CFormLabel, CButton, CBadge, CInputGroup, CInputGroupText,
  CSpinner, CTable, CTableHead, CTableRow, CTableHeaderCell,
  CTableBody, CTableDataCell, CFormSelect,
  CModal, CModalHeader, CModalTitle, CModalBody, CModalFooter
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilSave, cilTrash, cilCalendar, cilPencil } from '@coreui/icons'
import { useOrganization } from '@clerk/react'
import { DAY_LABELS } from '../../constants'
import { formatDate, normalizeTimeLabel } from '../../utils/formatUtils'
import { TXT, EVENT_TYPE_LABELS } from '../../utils/terminology'
import { getApiErrorCode, getApiErrorMessage } from '../../utils/apiErrors'
import {
  gridConfigurationToFormData,
  timeslotsToGridFormData,
  toGridConfigurationPayload,
  toGridTimeslotsPayload,
  toSchoolSettingsPayload,
} from '../../utils/schoolConfigPayloads'
import { timeOfDayToMinutes } from '../../utils/timeOfDay'
import { useAttemptScope } from '../../hooks/useAttemptScope'
import FeedbackBanner from '../../components/FeedbackBanner'
import StatePanel from '../../components/StatePanel'
import ConfirmationModal from '../../components/ConfirmationModal'
import PortugueseDateInput from '../../components/PortugueseDateInput'
import { TimeField } from '../../components/TimeField'
import { GENERATION_STATUS_LABELS } from '../../utils/presentation'
import { useClasses, useTimeslots } from '../catalog/data'
import { useGenerateSchedule, useSchedulerStatus } from '../scheduling/data'
import { normalizeBreakOverrides, validateBreakOverrides } from '../timetable/breakTimeline'
import { BreakTimelineModal } from './BreakTimelineModal'
import {
  useCalendarEvents,
  useCreateCalendarEvent,
  useDeleteCalendarEvent,
  useGridChangePending,
  useGridChangePreview,
  useGridChangePropose,
  useGridConfiguration,
  useGridSettings,
  usePreviewCalendarEventChange,
  useRegenerateGrid,
  useSchoolSettings,
  useSoftResetSchoolYear,
  useUpdateCalendarEvent,
  useUpsertSchoolSettings,
} from './data'

const EMPTY_CALENDAR_EVENT = {
  name: '', start_date: '', end_date: '', event_type: 'school_break', class_ids: [],
}

function flowResultMessage(result) {
  if (result.removedCount > 0) return `${result.removedCount} aula(s) saíram do horário ativo. `
  if (result.scopeChanged) return 'As datas ficaram bloqueadas para as turmas associadas. '
  if (result.isEdit) return 'O nome foi atualizado sem alterar o horário. '
  return 'O fluxo ficou sem turmas associadas e não altera o horário. '
}

function deleteEventMessage(event) {
  if (!event) return ''
  if (event.event_type === 'internship_flow') {
    return `O fluxo “${event.name}” será eliminado. As aulas já retiradas não são repostas automaticamente.`
  }
  return `O evento “${event.name}” será eliminado. Esta ação não pode ser desfeita.`
}

export const CalendarSection = () => {
  const [newEvent, setNewEvent] = useState(EMPTY_CALENDAR_EVENT)
  const [editingFlowId, setEditingFlowId] = useState(null)
  const [editingFlowOriginal, setEditingFlowOriginal] = useState(null)
  const [classFilter, setClassFilter] = useState('')
  const [previewState, setPreviewState] = useState(null)
  const [lastFlowResult, setLastFlowResult] = useState(null)
  const [showGenerateConfirm, setShowGenerateConfirm] = useState(false)
  const [stalePreviewMsg, setStalePreviewMsg] = useState('')
  const attemptScope = useAttemptScope()

  const { data: events = [], isLoading } = useCalendarEvents()
  const { data: classes = [] } = useClasses()
  const settingsQuery = useSchoolSettings()
  const settingsMutation = useUpsertSchoolSettings()
  const createMutation = useCreateCalendarEvent()
  const updateMutation = useUpdateCalendarEvent()
  const deleteMutation = useDeleteCalendarEvent()
  const previewMutation = usePreviewCalendarEventChange()
  const generateMutation = useGenerateSchedule()
  const [fieldErrors, setFieldErrors] = useState({})
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [automaticHolidaysOverride, setAutomaticHolidaysOverride] = useState(null)
  const automaticHolidaysEnabled = automaticHolidaysOverride ?? Boolean(
    settingsQuery.data?.automatic_holidays_enabled,
  )

  const isFlow = newEvent.event_type === 'internship_flow'
  const classesById = new Map(classes.map((item) => [item.id, item.name]))
  const isSavingFlow = createMutation.isPending || updateMutation.isPending

  const resetForm = () => {
    setNewEvent(EMPTY_CALENDAR_EVENT)
    setEditingFlowId(null)
    setEditingFlowOriginal(null)
    setClassFilter('')
    setFieldErrors({})
  }

  const validateForm = () => {
    const errors = {}
    if (!newEvent.name.trim()) errors.name = 'Indique o nome do evento.'
    if (!newEvent.start_date) errors.start_date = 'Indique a data de início.'
    if (!newEvent.end_date) errors.end_date = 'Indique a data de fim.'
    if (newEvent.start_date && newEvent.end_date && newEvent.end_date < newEvent.start_date) errors.end_date = 'A data de fim deve ser posterior ou igual à data de início.'
    setFieldErrors(errors)
    return Object.keys(errors).length === 0
  }

  const handleMutationError = (error) => {
    if (getApiErrorCode(error) === 'CALENDAR_EVENT_STALE') {
      setPreviewState(null)
      setStalePreviewMsg('As aulas afetadas mudaram. Repita a pré-visualização antes de guardar.')
      return
    }
    toast.error(getApiErrorMessage(error, 'Não foi possível guardar o fluxo de estágio.'))
  }

  const submitFlow = (fingerprint, removedCount = 0) => {
    const payload = {
      name: newEvent.name.trim(),
      start_date: newEvent.start_date,
      end_date: newEvent.end_date,
      class_ids: newEvent.class_ids,
      confirmation_fingerprint: fingerprint ?? null,
    }
    if (!editingFlowId) payload.event_type = 'internship_flow'
    const sortedClassIds = (ids) => [...ids].sort((left, right) => left - right).join(',')
    const scopeChanged = editingFlowOriginal
      ? (
        editingFlowOriginal.start_date !== newEvent.start_date
        || editingFlowOriginal.end_date !== newEvent.end_date
        || sortedClassIds(editingFlowOriginal.class_ids) !== sortedClassIds(newEvent.class_ids)
      )
      : newEvent.class_ids.length > 0
    const options = attemptScope.guard({
      onSuccess: () => {
        toast.success(editingFlowId ? 'Fluxo de estágio atualizado.' : 'Fluxo de estágio criado.')
        setStalePreviewMsg('')
        setLastFlowResult({
          name: payload.name,
          removedCount,
          scopeChanged,
          isEdit: Boolean(editingFlowId),
        })
        setPreviewState(null)
        resetForm()
      },
      onError: handleMutationError,
    })
    if (editingFlowId) {
      updateMutation.mutate({ id: editingFlowId, ...payload }, options)
    } else {
      createMutation.mutate(payload, options)
    }
  }

  const prepareFlowPreview = () => {
    setStalePreviewMsg('')
    previewMutation.reset()
    previewMutation.mutate({
      operation: editingFlowId ? 'update' : 'create',
      event_id: editingFlowId,
      name: newEvent.name.trim(),
      start_date: newEvent.start_date,
      end_date: newEvent.end_date,
      class_ids: newEvent.class_ids,
    }, attemptScope.guard({
      onSuccess: (data) => {
        if (data.requires_confirmation) {
          setPreviewState(data)
        } else {
          submitFlow(data.confirmation_fingerprint, 0)
        }
      },
      onError: handleMutationError,
    }))
  }

  const handleSubmit = () => {
    if (!validateForm()) return
    if (isFlow) {
      prepareFlowPreview()
      return
    }
    createMutation.mutate(
      {
        name: newEvent.name.trim(),
        start_date: newEvent.start_date,
        end_date: newEvent.end_date,
        event_type: newEvent.event_type,
      },
      attemptScope.guard({
        onSuccess: () => {
          resetForm()
          toast.success('Evento adicionado.')
        },
        onError: (error) => toast.error(
          getApiErrorMessage(error, 'Não foi possível adicionar evento. Verifique as datas e tente novamente.'),
        ),
      }),
    )
  }

  const startEditingFlow = (event) => {
    setEditingFlowId(event.id)
    setEditingFlowOriginal({
      start_date: event.start_date,
      end_date: event.end_date,
      class_ids: event.class_ids || [],
    })
    setNewEvent({
      name: event.name,
      start_date: event.start_date,
      end_date: event.end_date,
      event_type: 'internship_flow',
      class_ids: event.class_ids || [],
    })
    setClassFilter('')
    setFieldErrors({})
    window.scrollTo(0, 0)
  }

  const handleGenerate = () => {
    generateMutation.reset()
    generateMutation.mutate({}, attemptScope.guard({
      onSuccess: () => toast.success('Regeneração pedida. Acompanhe a proposta em Horários.'),
      onError: (error) => toast.error(
        getApiErrorMessage(error, 'Não foi possível regenerar o horário.', 'schedule.generate'),
      ),
    }))
  }

  const appliesToLabel = (event) => {
    if (event.event_type !== 'internship_flow') return 'Toda a escola'
    if (!event.class_ids?.length) return 'Sem turmas'
    return event.class_ids.map((id) => classesById.get(id) ?? `Turma ${id}`).join(', ')
  }

  const visibleClasses = classes.filter((item) => (
    (!item.is_archived || newEvent.class_ids.includes(item.id))
    && item.name?.toLowerCase().includes(classFilter.trim().toLowerCase())
  ))

  const sortedEvents = [...events].sort((left, right) => left.start_date.localeCompare(right.start_date))
  let eventListContent
  if (isLoading) eventListContent = <StatePanel state="loading" title="A carregar eventos" compact />
  else if (sortedEvents.length === 0) eventListContent = <StatePanel state="empty" title="Sem interrupções registadas" description="Ative os feriados automáticos ou adicione uma interrupção manual." compact />
  else eventListContent = (
      <CTable striped hover responsive>
        <CTableHead>
          <CTableRow>
            <CTableHeaderCell>Nome</CTableHeaderCell>
            <CTableHeaderCell>Início</CTableHeaderCell>
            <CTableHeaderCell>Fim</CTableHeaderCell>
            <CTableHeaderCell>Tipo</CTableHeaderCell>
            <CTableHeaderCell>Aplica-se a</CTableHeaderCell>
            <CTableHeaderCell>Origem</CTableHeaderCell>
            <CTableHeaderCell />
          </CTableRow>
        </CTableHead>
        <CTableBody>
          {sortedEvents.map((ev) => (
            <CTableRow key={ev.id}>
              <CTableDataCell>{ev.name}</CTableDataCell>
              <CTableDataCell className="text-nowrap">{formatDate(ev.start_date)}</CTableDataCell>
              <CTableDataCell className="text-nowrap">{formatDate(ev.end_date)}</CTableDataCell>
              <CTableDataCell>{EVENT_TYPE_LABELS[ev.event_type] ?? ev.event_type}</CTableDataCell>
              <CTableDataCell>
                {appliesToLabel(ev)}
                {ev.applies_to_current_school_year === false && (
                  <CBadge color="secondary" className="ms-2">Ano letivo anterior</CBadge>
                )}
              </CTableDataCell>
              <CTableDataCell>
                <CBadge color={ev.source === 'auto' ? 'info' : 'secondary'}>
                  {ev.source === 'auto' ? 'Automático' : 'Manual'}
                </CBadge>
              </CTableDataCell>
              <CTableDataCell className="text-nowrap">
                {ev.event_type === 'internship_flow'
                  && ev.source === 'manual'
                  && ev.applies_to_current_school_year !== false && (
                  <CButton
                    color="primary"
                    variant="ghost"
                    size="sm"
                    aria-label={`Editar ${ev.name}`}
                    onClick={() => startEditingFlow(ev)}
                  >
                    <CIcon icon={cilPencil} />
                  </CButton>
                )}
                <CButton
                  color="danger"
                  variant="ghost"
                  size="sm"
                  disabled={deleteMutation.isPending}
                  aria-label={`Remover ${ev.name}`}
                  onClick={() => setDeleteTarget(ev)}
                >
                  <CIcon icon={cilTrash} />
                </CButton>
              </CTableDataCell>
            </CTableRow>
          ))}
        </CTableBody>
      </CTable>
    )

  let submitLabel = 'Adicionar evento'
  if (editingFlowId) submitLabel = isSavingFlow ? 'A guardar…' : 'Guardar fluxo'
  else if (isFlow) submitLabel = previewMutation.isPending ? 'A analisar' : 'Pré-visualizar e guardar'

  return (
    <div>
      {stalePreviewMsg && <div className="mb-3"><FeedbackBanner tone="warning">{stalePreviewMsg}</FeedbackBanner></div>}
      {lastFlowResult && (
        <div className="mb-3">
          <FeedbackBanner
            tone="info"
            action={lastFlowResult.scopeChanged ? (
              <button type="button" onClick={() => setShowGenerateConfirm(true)}>
                Regenerar horário
              </button>
            ) : null}
          >
            {flowResultMessage(lastFlowResult)}
            Fluxo “{lastFlowResult.name}” guardado.
          </FeedbackBanner>
        </div>
      )}
      {settingsMutation.isError && (
        <FeedbackBanner tone="danger">
          {getApiErrorMessage(settingsMutation.error, 'Não foi possível guardar a preferência de feriados automáticos.')}
        </FeedbackBanner>
      )}


      <section className="mb-4 calendar-event-editor" aria-label="Editar calendário">
        <h3 className="h6 fw-bold py-2 calendar-event-editor__header">
          <span>
            <CIcon icon={cilCalendar} className="me-2" />
            {editingFlowId ? 'Editar Fluxo de estágio' : 'Adicionar Evento'}
          </span>
        </h3>
        <div>
          <details className="context-details mb-3">
          <summary>Como funciona o calendário</summary>
          <p className="text-muted mb-0 mt-2">
            Registe uma interrupção específica da escola ou um fluxo de estágio.
            {' '}Os feriados nacionais são atualizados automaticamente através desta opção.
          </p>
          </details>
          <CRow className="g-3">
            <CCol md={3}>
              <CFormLabel htmlFor="eventName">Nome do evento</CFormLabel>
              <CFormInput
                id="eventName"
                placeholder={isFlow ? 'Ex: Estágio 10.º ano' : 'Ex: Férias de Natal'}
                value={newEvent.name}
                onChange={(e) => setNewEvent((p) => ({ ...p, name: e.target.value }))}
                invalid={Boolean(fieldErrors.name)}
              />
              {fieldErrors.name && <div className="text-danger small mt-1">{fieldErrors.name}</div>}
            </CCol>
            <CCol md={2}>
              <CFormLabel htmlFor="eventStart">Início</CFormLabel>
              <PortugueseDateInput
                id="eventStart"
                value={newEvent.start_date}
                onChange={(value) => setNewEvent((p) => ({ ...p, start_date: value }))}
                invalid={Boolean(fieldErrors.start_date)}
              />
              {fieldErrors.start_date && <div className="text-danger small mt-1">{fieldErrors.start_date}</div>}
            </CCol>
            <CCol md={2}>
              <CFormLabel htmlFor="eventEnd">Fim</CFormLabel>
              <PortugueseDateInput
                id="eventEnd"
                value={newEvent.end_date}
                onChange={(value) => setNewEvent((p) => ({ ...p, end_date: value }))}
                invalid={Boolean(fieldErrors.end_date)}
              />
              {fieldErrors.end_date && <div className="text-danger small mt-1">{fieldErrors.end_date}</div>}
            </CCol>
            <CCol md={3}>
              <CFormLabel htmlFor="eventType">Tipo</CFormLabel>
              <CFormSelect
                id="eventType"
                value={newEvent.event_type}
                disabled={Boolean(editingFlowId)}
                onChange={(e) => setNewEvent((p) => ({ ...p, event_type: e.target.value, class_ids: [] }))}
              >
                <option value="school_break">Pausa escolar</option>
                <option value="exam_period">Período de exames</option>
                <option value="internship_flow">Fluxo de estágio</option>
                <option value="other">Outro</option>
              </CFormSelect>
            </CCol>
            <CCol xs={12} xl="auto" className="d-flex align-items-end">
              <CButton
                color="primary"
                className="text-nowrap"
                onClick={handleSubmit}
                disabled={createMutation.isPending || updateMutation.isPending || previewMutation.isPending}
              >
                {submitLabel}
              </CButton>
            </CCol>
          </CRow>

          {isFlow && (
            <CRow className="g-3 mt-1">
              <CCol md={8}>
                <CFormLabel htmlFor="eventClassSearch">Turmas abrangidas (opcional)</CFormLabel>
                <CFormInput
                  id="eventClassSearch"
                  placeholder="Pesquisar turma..."
                  value={classFilter}
                  onChange={(e) => setClassFilter(e.target.value)}
                  aria-describedby="eventClassSearchHelp"
                />
                <fieldset
                  id="eventClassOptions"
                  aria-label="Turmas abrangidas"
                  className="border rounded p-2 mt-2"
                  style={{ maxHeight: '180px', overflowY: 'auto' }}
                >
                  {visibleClasses.length === 0 && (
                    <span className="text-muted small">Sem turmas para o filtro indicado.</span>
                  )}
                  {visibleClasses.map((item) => (
                    <CFormCheck
                      key={item.id}
                      id={`event-class-${item.id}`}
                      label={item.name}
                      checked={newEvent.class_ids.includes(item.id)}
                      onChange={(e) => setNewEvent((p) => ({
                        ...p,
                        class_ids: e.target.checked
                          ? [...p.class_ids, item.id]
                          : p.class_ids.filter((id) => id !== item.id),
                      }))}
                    />
                  ))}
                </fieldset>
                <div id="eventClassSearchHelp" className="form-text">
                  Sem turmas, o fluxo não bloqueia aulas. As aulas afetadas saem do horário quando guardar.
                </div>
              </CCol>
              {editingFlowId && (
                <CCol md={4} className="d-flex align-items-end">
                  <CButton color="secondary" variant="outline" onClick={resetForm}>
                    Cancelar edição
                  </CButton>
                </CCol>
              )}
            </CRow>
          )}
        </div>
      </section>

      <section className="compact-row mb-4" aria-label="Preferência de feriados">
          <CFormCheck
            id="school-automatic-holidays"
            label="Feriados automáticos"
            checked={automaticHolidaysEnabled}
            disabled={settingsQuery.isLoading || settingsMutation.isPending}
            onChange={(event) => {
              const enabled = event.target.checked
              setAutomaticHolidaysOverride(enabled)
              settingsMutation.mutate(
                { automatic_holidays_enabled: enabled },
                attemptScope.guard({
                  onSuccess: () => {
                    setAutomaticHolidaysOverride(null)
                    toast.success(
                      enabled
                        ? 'Feriados automáticos ativados.'
                        : 'Feriados automáticos desativados. Os eventos existentes foram preservados.',
                    )
                  },
                  onError: () => setAutomaticHolidaysOverride(null),
                }),
              )
            }}
          />
          <p className="text-muted small mb-0 mt-2">
            Ativar importa os feriados nacionais e acompanha alterações futuras às datas do período letivo.
          </p>
      </section>

      {eventListContent}

      <CModal
        visible={Boolean(previewState)}
        onClose={() => setPreviewState(null)}
        size="lg"
        backdrop="static"
      >
        <CModalHeader>
          <CModalTitle>Confirmar alteração do horário</CModalTitle>
        </CModalHeader>
        <CModalBody>
          <div className="mb-3"><FeedbackBanner tone="warning">{previewState?.message}</FeedbackBanner></div>
          <CTable small responsive>
            <CTableHead>
              <CTableRow>
                <CTableHeaderCell>Turma</CTableHeaderCell>
                <CTableHeaderCell>Data</CTableHeaderCell>
                <CTableHeaderCell>Disciplina</CTableHeaderCell>
              </CTableRow>
            </CTableHead>
            <CTableBody>
              {previewState?.affected_lessons.map((lesson) => (
                <CTableRow key={lesson.lesson_id}>
                  <CTableDataCell>{lesson.class_name ?? 'Turma'}</CTableDataCell>
                  <CTableDataCell className="text-nowrap">{formatDate(lesson.date)}</CTableDataCell>
                  <CTableDataCell>{lesson.subject_name ?? 'Disciplina'}</CTableDataCell>
                </CTableRow>
              ))}
            </CTableBody>
          </CTable>
        </CModalBody>
        <CModalFooter>
          <CButton
            color="secondary"
            variant="outline"
            onClick={() => setPreviewState(null)}
            disabled={isSavingFlow}
          >
            {TXT.CANCEL}
          </CButton>
          <CButton
            color="primary"
            onClick={() => submitFlow(
              previewState?.confirmation_fingerprint,
              previewState?.affected_lessons?.length ?? 0,
            )}
            disabled={isSavingFlow}
          >
            {isSavingFlow ? 'A guardar…' : 'Confirmar e guardar'}
          </CButton>
        </CModalFooter>
      </CModal>

      <ConfirmationModal
        visible={showGenerateConfirm}
        onClose={() => setShowGenerateConfirm(false)}
        onConfirm={() => {
          setShowGenerateConfirm(false)
          handleGenerate()
        }}
        title="Regenerar horário"
        message="A regeneração analisa o horário com o estágio já aplicado e propõe as alterações necessárias. Pretende continuar?"
        confirmText="Regenerar horário"
        isLoading={generateMutation.isPending}
        variant="warning"
      />

      <ConfirmationModal
        visible={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          deleteMutation.mutate(deleteTarget.id, attemptScope.guard({
            onSuccess: () => {
              setDeleteTarget(null)
              toast.success('Evento eliminado.')
            },
            onError: (error) => {
              setDeleteTarget(null)
              toast.error(getApiErrorMessage(error, 'Não foi possível remover o evento. Tente novamente.'))
            },
          }))
        }}
        title="Remover evento"
        message={deleteEventMessage(deleteTarget)}
        confirmText="Remover"
        pendingText="A remover…"
        isLoading={deleteMutation.isPending}
      />
    </div>
  )
}
function toSettingsForm(settings) {
  const form = {
    school_start_date: settings?.school_start_date || '',
    school_hard_end_date: settings?.school_hard_end_date || '',
    preferred_end_date: settings?.preferred_end_date || '',
    repair_stability_window_days: settings?.repair_stability_window_days?.toString() || '14',
  }
  if (settings?.automatic_holidays_enabled !== undefined) {
    form.automatic_holidays_enabled = Boolean(settings.automatic_holidays_enabled)
  }
  return form
}

function validateSettingsForm(form) {
  if (!form.school_start_date || !form.school_hard_end_date) {
    return 'Por favor, preencha todas as datas antes de guardar.'
  }
  if (form.school_hard_end_date <= form.school_start_date) {
    return 'A data-limite deve ser posterior à data de início.'
  }
  if (
    form.preferred_end_date
    && (
      form.preferred_end_date < form.school_start_date
      || form.preferred_end_date > form.school_hard_end_date
    )
  ) {
    return 'A data preferencial deve ficar entre o início das aulas e a data-limite.'
  }
  return ''
}

export const SettingsSection = () => {
  const { data: settings, isLoading } = useSchoolSettings()
  if (isLoading) return <div className="d-flex justify-content-center p-5"><CSpinner /></div>

  const editorKey = `${settings?.school_start_date ?? ''}:${settings?.school_hard_end_date ?? ''}:${settings?.preferred_end_date ?? ''}:${settings?.repair_stability_window_days ?? ''}:${settings?.automatic_holidays_enabled ?? ''}`
  return <SettingsEditor key={editorKey} settings={settings} />
}

const SettingsEditor = ({ settings }) => {
  const [savePromptMsg, setSavePromptMsg] = useState(null)
  const [showSaveModal, setShowSaveModal] = useState(false)
  const [form, setForm] = useState(() => toSettingsForm(settings))

  // Soft-Reset state
  const [showResetModal, setShowResetModal] = useState(false)
  const [resetConfirmText, setResetConfirmText] = useState('')
  const [resetChecked, setResetChecked] = useState(false)
  const [resetError, setResetError] = useState('')

  const resetMutation = useSoftResetSchoolYear()
  const attemptScope = useAttemptScope()

  const handleSoftReset = () => {
    setResetError('')
    if (resetConfirmText !== 'Confirmo' || !resetChecked) return
    resetMutation.mutate({ confirm_phrase: resetConfirmText }, attemptScope.guard({
      onSuccess: () => {
        toast.success('Ano letivo recomeçado. Os horários deixaram de estar ativos.')
        setShowResetModal(false)
        setResetConfirmText('')
        setResetChecked(false)
        window.scrollTo(0, 0)
      },
      onError: (err) => {
        setResetError(getApiErrorMessage(err, 'Não foi possível recomeçar ano letivo.'))
      },
    }))
  }

  const updateForm = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }))
    setSavePromptMsg(null)
  }

  const upsertMutation = useUpsertSchoolSettings()

  const handleSave = () => {
    const validationMessage = validateSettingsForm(form)
    if (validationMessage) {
      setSavePromptMsg(validationMessage)
      return
    }
    setShowSaveModal(true)
  }

  const confirmSave = () => {
    upsertMutation.mutate(toSchoolSettingsPayload(form), attemptScope.guard({
      onSuccess: () => {
        toast.success('Período letivo guardado.')
        setSavePromptMsg(null)
        setShowSaveModal(false)
      },
      onError: () => setShowSaveModal(false),
    }))
  }

  const canDisableAutomaticHolidays = getApiErrorCode(upsertMutation.error) === 'HOLIDAY_SYNC_FAILED'
    && form.automatic_holidays_enabled

  const handleDisableAutomaticHolidays = () => {
    const validationMessage = validateSettingsForm(form)
    if (validationMessage) {
      setSavePromptMsg(validationMessage)
      return
    }
    upsertMutation.mutate(
      { ...toSchoolSettingsPayload(form), automatic_holidays_enabled: false },
      attemptScope.guard({
        onSuccess: () => {
          setForm((current) => ({ ...current, automatic_holidays_enabled: false }))
          toast.success('Período letivo guardado com os feriados automáticos desativados.')
          setSavePromptMsg(null)
        },
      }),
    )
  }

  return (
    <div>
      {savePromptMsg && <div className="mb-3"><FeedbackBanner tone="warning">{savePromptMsg}</FeedbackBanner></div>}
      {upsertMutation.isError && (
        <div className="mb-3">
          <FeedbackBanner
            tone="danger"
            action={canDisableAutomaticHolidays && (
              <CButton
                color="link"
                className="p-0"
                onClick={handleDisableAutomaticHolidays}
                disabled={upsertMutation.isPending}
              >
                Desativar feriados automáticos e guardar
              </CButton>
            )}
          >
            {getApiErrorMessage(upsertMutation.error, 'Não foi possível guardar a configuração.')}
          </FeedbackBanner>
        </div>
      )}
      
      <CRow className="g-3 mb-3 align-items-start">
        <CCol md={3}>
          <CFormLabel htmlFor="startDate" className="school-config-field-label">Início das Aulas</CFormLabel>
          <PortugueseDateInput
            id="startDate"
            value={form.school_start_date}
            onChange={(value) => updateForm('school_start_date', value)}
            text="Data oficial de início do semestre"
          />
        </CCol>
        <CCol md={3}>
          <CFormLabel htmlFor="hardEndDate" className="school-config-field-label">Data limite final</CFormLabel>
          <PortugueseDateInput
            id="hardEndDate"
            value={form.school_hard_end_date}
            onChange={(value) => updateForm('school_hard_end_date', value)}
            text="Não há aulas após esta data"
          />
        </CCol>
        <CCol md={3}>
          <CFormLabel htmlFor="preferredEndDate" className="school-config-field-label">Data preferencial de fim</CFormLabel>
          <PortugueseDateInput
            id="preferredEndDate"
            value={form.preferred_end_date}
            onChange={(value) => updateForm('preferred_end_date', value)}
            text="Data desejada para o fim das aulas; tem de ser anterior à data limite"
          />
        </CCol>
        <CCol md={3}>
          <CFormLabel htmlFor="repairWindow" className="school-config-field-label">Dias em que o horário não muda</CFormLabel>
          <CInputGroup>
            <CFormInput
              id="repairWindow"
              type="number"
              min={0}
              value={form.repair_stability_window_days}
              aria-describedby="repairWindow-unit repairWindow-help"
              onChange={(e) => updateForm('repair_stability_window_days', e.target.value)}
            />
            <CInputGroupText id="repairWindow-unit">Dias</CInputGroupText>
          </CInputGroup>
          <div id="repairWindow-help" className="form-text">Com 0, hoje pode mudar; com 1, hoje fica intacto.</div>
        </CCol>
      </CRow>
      
      <div className="d-flex justify-content-between align-items-center mt-3">
        <CButton
          color="danger"
          variant="outline"
          size="sm"
          onClick={() => setShowResetModal(true)}
        >
           Recomeçar ano letivo
        </CButton>
        <CButton color="primary" onClick={handleSave} disabled={upsertMutation.isPending}>
          <CIcon icon={cilSave} className="me-1" />
           {upsertMutation.isPending ? 'A guardar…' : 'Guardar alterações'}
        </CButton>
      </div>

      <ConfirmationModal
        visible={showSaveModal}
        onClose={() => setShowSaveModal(false)}
        onConfirm={confirmSave}
        title="Guardar novas datas?"
        message="As novas datas alteram o período usado pelo gerador de horários. Confirme para guardar estas alterações."
        confirmText="Guardar alterações"
        isLoading={upsertMutation.isPending}
        variant="primary"
      />

      <CModal visible={showResetModal} onClose={() => { setShowResetModal(false); setResetError(''); setResetConfirmText(''); setResetChecked(false); }} backdrop="static">
        <CModalHeader>
          <CModalTitle className="text-danger fw-bold">Recomeçar ano letivo</CModalTitle>
        </CModalHeader>
        <CModalBody>
          <div className="mb-3">
            <FeedbackBanner tone="warning">
              Esta ação repõe o ano letivo no estado inicial: os horários publicados deixam de estar ativos, as propostas pendentes são invalidadas e o progresso da geração volta a zero. O histórico é conservado, mas deixa de influenciar novas gerações.
            </FeedbackBanner>
          </div>

          {resetError && <div className="mb-3"><FeedbackBanner tone="danger">{resetError}</FeedbackBanner></div>}

          <div className="mb-3 mt-4">
            <CFormCheck 
              id="resetCheck"
              label="Compreendo que os horários ativos e o progresso passam a zero."
              checked={resetChecked}
              onChange={(e) => setResetChecked(e.target.checked)}
            />
          </div>

          <div className="mb-3">
            <CFormLabel htmlFor="confirmWord">Para confirmar, digite exatamente a palavra: <strong>Confirmo</strong></CFormLabel>
            <CFormInput 
              id="confirmWord"
              value={resetConfirmText}
              onChange={(e) => setResetConfirmText(e.target.value)}
              placeholder="Confirmo"
            />
          </div>
        </CModalBody>
        <CModalFooter>
          <CButton color="secondary" variant="outline" onClick={() => setShowResetModal(false)}>
            {TXT.CANCEL}
          </CButton>
          <CButton 
            color="danger" 
            className="text-white"
            disabled={resetConfirmText !== 'Confirmo' || !resetChecked || resetMutation.isPending}
            onClick={handleSoftReset}
          >
            {resetMutation.isPending ? 'A recomeçar' : 'Confirmar reinício'}
          </CButton>
        </CModalFooter>
      </CModal>
    </div>
  )
}

export const GridSection = () => {
  const orgId = useOrganization().organization?.id
  const configurationQuery = useGridConfiguration()
  const settingsQuery = useGridSettings()
  const timeslotsQuery = useTimeslots()
  const statusQuery = useSchedulerStatus()
  const pendingQuery = useGridChangePending()

  if (
    configurationQuery.isLoading
    || settingsQuery.isLoading
    || timeslotsQuery.isLoading
    || statusQuery.isLoading
  ) {
    return <div className="school-config-skeleton" aria-busy="true"><span className="skeleton" /><span className="skeleton" /><span className="skeleton" /><span className="skeleton" /></div>
  }
  const queryError = configurationQuery.error || settingsQuery.error || timeslotsQuery.error
  if (queryError) {
    return <FeedbackBanner tone="danger">{getApiErrorMessage(queryError, 'Não foi possível carregar a grelha.')}</FeedbackBanner>
  }

  const storedConfiguration = configurationQuery.data?.source === 'VERSION'
    && configurationQuery.data.configuration
    ? configurationQuery.data.configuration
    : null

  let initialFormData
  try {
    initialFormData = storedConfiguration
      ? gridConfigurationToFormData(storedConfiguration)
      : timeslotsToGridFormData(timeslotsQuery.data)
  } catch (error) {
    return (
      <div>
        <div className="mb-3"><FeedbackBanner tone="danger">{error.message}</FeedbackBanner></div>
        <CButton color="primary" disabled>Guardar e Regenerar Grelha</CButton>
      </div>
    )
  }
  const data = settingsQuery.data
  const initialGridSettings = {
    lunch_window_start: normalizeTimeLabel(data?.lunch_window_start) || '12:00',
    lunch_window_end: normalizeTimeLabel(data?.lunch_window_end) || '14:00',
    lunch_min_duration_minutes: data?.lunch_min_duration_minutes ?? 60,
  }

  return (
    <GridEditor
      key={orgId}
      orgId={orgId}
      initialFormData={initialFormData}
      initialGridSettings={initialGridSettings}
      schoolYearPublished={statusQuery.data?.school_year_publication_state === 'PUBLISHED'}
      pendingProposal={pendingQuery.data}
    />
  )
}

const RULE_TYPE_LABELS = {
  CLASS_DAY_OFF: 'Regra de dia sem aulas',
}

const PendingProposalBanner = ({ proposal }) => {
  if (!proposal?.grid_version_id) return null
  const statusLabel = GENERATION_STATUS_LABELS[proposal.job_status] ?? 'Em processamento'
  return (
    <FeedbackBanner
      tone="info"
      action={<a href="/schedules">Ir para Horários</a>}
    >
      <strong>Proposta de grelha pendente</strong>
      {' — '}efetiva a {formatDate(proposal.effective_date)}
      {statusLabel ? ` · ${statusLabel}` : ''}. O cancelamento da proposta é feito em Horários.
    </FeedbackBanner>
  )
}

/** "{p} professor(es) e {t} turma(s)" com a parte zerada omitida. */
const availabilityCountLabel = (target) => {
  const teachers = Array.isArray(target.teachers) ? target.teachers.length : 0
  const classes = Array.isArray(target.classes) ? target.classes.length : 0
  const parts = []
  if (teachers) parts.push(`${teachers} professor(es)`)
  if (classes) parts.push(`${classes} turma(s)`)
  return parts.length ? `${parts.join(' e ')} com disponibilidade neste bloco.` : 'Sem disponibilidade neste bloco.'
}

const GridChangeImpactPanel = ({ preview, decisions, onDecision, onPropose, isProposing }) => {
  const decisionTargets = []
  const seen = new Set()
  for (const entry of [...preview.affected_availabilities, ...preview.affected_constraints]) {
    if (!entry.requires_decision || seen.has(entry.current_timeslot_id)) continue
    seen.add(entry.current_timeslot_id)
    decisionTargets.push(entry)
  }
  const missing = decisionTargets.filter((target) => !decisions[target.current_timeslot_id])
  const changedDays = preview.daily.filter((day) => day.delta !== 0)

  return (
    <CCard className="border-0 shadow-sm mb-4">
      <CCardHeader className="bg-white fw-bold py-2">Impacto da alteração</CCardHeader>
      <CCardBody>
        <p className="mb-2">
          Primeira data editável: <strong>{formatDate(preview.first_editable_date)}</strong>
        </p>
        <p className="text-muted small mb-3">
          {preview.minutes_completed} min já dadas · {preview.minutes_protected} min que não mudam ·{' '}
          {preview.minutes_planned_after_boundary} min previstos depois da data de corte ·{' '}
          {preview.minutes_remaining} min por agendar
        </p>

        {!preview.can_propose && (
          <div className="mb-3">
            <FeedbackBanner tone="warning">
              <strong>Esta alteração não pode ser proposta:</strong>
              <ul className="mb-0">
                {preview.blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}
              </ul>
            </FeedbackBanner>
          </div>
        )}

        <h6 className="fw-bold text-secondary mb-2">Diferença de aulas por dia</h6>
        {changedDays.length === 0 ? (
          <p className="text-muted small">Sem alterações no número de aulas por dia.</p>
        ) : (
          <CTable small responsive className="mb-3">
            <CTableHead>
              <CTableRow>
                <CTableHeaderCell>Dia</CTableHeaderCell>
                <CTableHeaderCell>Aulas atuais</CTableHeaderCell>
                <CTableHeaderCell>Aulas propostas</CTableHeaderCell>
                <CTableHeaderCell>Diferença</CTableHeaderCell>
              </CTableRow>
            </CTableHead>
            <CTableBody>
              {changedDays.map((day) => (
                <CTableRow key={day.day_of_week}>
                  <CTableDataCell>{DAY_LABELS[day.day_of_week]}</CTableDataCell>
                  <CTableDataCell>{day.current_lessons}</CTableDataCell>
                  <CTableDataCell>{day.proposed_lessons}</CTableDataCell>
                  <CTableDataCell>{day.delta > 0 ? `+${day.delta}` : day.delta}</CTableDataCell>
                </CTableRow>
              ))}
            </CTableBody>
          </CTable>
        )}

        {decisionTargets.length > 0 && (
          <>
            <h6 className="fw-bold text-secondary mb-2">Aulas, disponibilidades e regras afetadas</h6>
            <p className="text-muted small mb-3">
              Escolha se cada bloco afetado é copiado para a nova grelha ou descartado.
            </p>
            {decisionTargets.map((target) => {
              const isAvailability = Array.isArray(target.teachers) || Array.isArray(target.classes)
              return (
                <fieldset key={target.current_timeslot_id} className="compact-row mb-3">
                  <legend className="fs-6 fw-semibold">
                    {isAvailability
                      ? `${DAY_LABELS[target.current.day_of_week]} ${normalizeTimeLabel(target.current.start_time)}-${normalizeTimeLabel(target.current.end_time)}`
                      : RULE_TYPE_LABELS[target.rule_type] || 'Regra'}
                  </legend>
                  <div className="text-muted small mb-2">
                    {isAvailability
                      ? availabilityCountLabel(target)
                      : 'Regra aplicada a este bloco horário.'}
                    {' '}
                    {target.proposed
                      ? `Novo bloco: ${DAY_LABELS[target.proposed.day_of_week]} ${normalizeTimeLabel(target.proposed.start_time)}-${normalizeTimeLabel(target.proposed.end_time)}.`
                      : 'Sem bloco de destino.'}
                  </div>
                  <CFormCheck
                    type="radio"
                    name={`grid-change-decision-${target.current_timeslot_id}`}
                    id={`grid-change-decision-${target.current_timeslot_id}-copy`}
                    label="Copiar"
                    checked={decisions[target.current_timeslot_id] === 'COPY'}
                    onChange={() => onDecision(target.current_timeslot_id, 'COPY')}
                  />
                  <CFormCheck
                    type="radio"
                    name={`grid-change-decision-${target.current_timeslot_id}`}
                    id={`grid-change-decision-${target.current_timeslot_id}-discard`}
                    label="Descartar"
                    checked={decisions[target.current_timeslot_id] === 'DISCARD'}
                    onChange={() => onDecision(target.current_timeslot_id, 'DISCARD')}
                  />
                </fieldset>
              )
            })}
          </>
        )}

        <div className="d-flex justify-content-end align-items-center gap-3">
          {preview.can_propose && missing.length > 0 && (
            <output className="text-danger small">
              Faltam decisões para {missing.length} bloco(s) afetado(s).
            </output>
          )}
          <CButton
            type="button"
            color="primary"
            disabled={!preview.can_propose || missing.length > 0 || isProposing}
            onClick={onPropose}
          >
            {isProposing ? 'A propor' : 'Propor alteração'}
          </CButton>
        </div>
      </CCardBody>
    </CCard>
  )
}

const GridEditor = ({
  orgId,
  initialFormData,
  initialGridSettings,
  schoolYearPublished,
  pendingProposal,
}) => {
  const [formData, setFormData] = useState(initialFormData)
  const [gridSettings, setGridSettings] = useState(initialGridSettings)
  const [preview, setPreview] = useState(null)
  const [decisions, setDecisions] = useState({})
  const [proposal, setProposal] = useState(null)
  const [breaksModalOpen, setBreaksModalOpen] = useState(false)
  const [validationMessage, setValidationMessage] = useState('')
  const [staleProposalMessage, setStaleProposalMessage] = useState('')

  const regenerateMutation = useRegenerateGrid()
  const previewMutation = useGridChangePreview()
  const proposeMutation = useGridChangePropose()
  const attemptScope = useAttemptScope()

  const applyFormData = (updater) => {
    setFormData(updater)
    setPreview(null)
    setDecisions({})
    setValidationMessage('')
  }

  const timeslotValues = {
    opening_time: formData.start_time,
    closing_time: formData.end_time,
    slot_duration_minutes: formData.slot_duration_minutes,
    break_duration_minutes: formData.break_duration_minutes,
    break_overrides: formData.break_overrides,
  }

  const validateForm = () => {
    const duration = Number(formData.slot_duration_minutes)
    const breakDuration = Number(formData.break_duration_minutes)
    const lunchDuration = Number(gridSettings.lunch_min_duration_minutes)
    const startMinutes = timeOfDayToMinutes(formData.start_time)
    const endMinutes = timeOfDayToMinutes(formData.end_time)
    const lunchStart = timeOfDayToMinutes(gridSettings.lunch_window_start)
    const lunchEnd = timeOfDayToMinutes(gridSettings.lunch_window_end)
    if (
      !Number.isFinite(startMinutes)
      || !Number.isFinite(endMinutes)
      || endMinutes <= startMinutes
      || !Number.isFinite(lunchStart)
      || !Number.isFinite(lunchEnd)
      || lunchEnd <= lunchStart
      || !Number.isFinite(duration)
      || duration <= 0
      || !Number.isFinite(breakDuration)
      || breakDuration < 0
      || !Number.isFinite(lunchDuration)
      || lunchDuration <= 0
      || !Object.values(formData.days).some(Boolean)
    ) {
      return 'Preencha uma grelha válida, com pelo menos um dia de funcionamento.'
    }
    if (lunchDuration > lunchEnd - lunchStart) return 'A duração mínima do almoço não pode exceder a janela configurada.'
    return validateBreakOverrides(timeslotValues) || null
  }

  const handlePreview = () => {
    const validationError = validateForm()
    if (validationError) {
      setValidationMessage(validationError)
      return
    }
    setValidationMessage('')
    setStaleProposalMessage('')
    previewMutation.reset()
    setProposal(null)
    previewMutation.mutate({ timeslots: toGridTimeslotsPayload(formData) }, attemptScope.guard({
      onSuccess: (data) => {
        setPreview(data)
        setDecisions({})
        setStaleProposalMessage('')
      },
      onError: (error) => {
        toast.error(getApiErrorMessage(error, 'Não foi possível pré-visualizar a alteração da grelha.'))
      },
    }))
  }

  const handlePropose = () => {
    if (!preview) return
    proposeMutation.reset()
    const decisionsPayload = Object.entries(decisions).map(([timeslotId, action]) => ({
      current_timeslot_id: Number(timeslotId),
      action,
    }))
    proposeMutation.mutate({
      timeslots: toGridTimeslotsPayload(formData),
      fingerprint: preview.fingerprint,
      decisions: decisionsPayload,
    }, attemptScope.guard({
      onSuccess: (data) => {
        setProposal(data)
        setPreview(null)
        setDecisions({})
        setStaleProposalMessage('')
      },
      onError: (error) => {
        if (getApiErrorCode(error) === 'GRID_CHANGE_STALE') {
          setPreview(null)
          setDecisions({})
          setStaleProposalMessage('A análise mudou desde a pré-visualização. Repita a pré-visualização antes de propor a alteração.')
          return
        }
        toast.error(getApiErrorMessage(error, 'Não foi possível propor a alteração da grelha.'))
      },
    }))
  }

  const handleSubmit = (event) => {
    event.preventDefault()
    if (schoolYearPublished) {
      handlePreview()
      return
    }
    regenerateMutation.reset()
    const validationError = validateForm()
    if (validationError) {
      setValidationMessage(validationError)
      return
    }
    setValidationMessage('')
    regenerateMutation.mutate(toGridConfigurationPayload({ formData, gridSettings }), attemptScope.guard({
      onSuccess: (payload) => {
        toast.success(payload.message)
      },
      onError: (error) => {
        toast.error(getApiErrorMessage(error, 'Não foi possível guardar a configuração da grelha.'))
      },
    }))
  }

  const toggleDay = (idx) => {
    applyFormData((prev) => ({ ...prev, days: { ...prev.days, [idx]: !prev.days[idx] } }))
  }

  const customBreakCount = normalizeBreakOverrides(formData.break_overrides).length
  const isSubmitting = schoolYearPublished ? previewMutation.isPending : regenerateMutation.isPending
  let submitLabel
  if (schoolYearPublished) {
    submitLabel = preview ? 'Repetir pré-visualização' : 'Pré-visualizar alteração'
  } else {
    submitLabel = regenerateMutation.isPending ? 'A regenerar' : 'Guardar e regenerar grelha'
  }

  return (
    <div>
      {validationMessage && <div className="mb-3"><FeedbackBanner tone="danger">{validationMessage}</FeedbackBanner></div>}
      {staleProposalMessage && <div className="mb-3"><FeedbackBanner tone="warning">{staleProposalMessage}</FeedbackBanner></div>}
      <div className="mb-3"><PendingProposalBanner proposal={pendingProposal} /></div>
      {proposal && (
        <div className="mb-3">
          <FeedbackBanner tone="success">
            <strong>Proposta de grelha criada.</strong>
            {' '}Fica efetiva a {formatDate(proposal.effective_date)}. Estado da geração:{' '}
            {GENERATION_STATUS_LABELS[proposal.status] ?? 'Em processamento'}.
            {' '}<a href="/schedules">Ir para Horários</a> para acompanhar a proposta.
          </FeedbackBanner>
        </div>
      )}

      <p className="text-muted mb-4">
        {schoolYearPublished
          ? 'O ano letivo está publicado. As alterações à grelha são analisadas e propostas antes de serem aplicadas.'
          : <>Defina aqui o funcionamento geral da escola. Ao guardar, a grelha horária base será <strong>regenerada</strong>.</>}
      </p>

      <CForm onSubmit={handleSubmit}>
        <CRow className="mb-4 align-items-start">
          <CCol md={3}>
            <TimeField id="gridStart" label="Abertura da Escola" value={formData.start_time} onChange={(value) => applyFormData((prev) => ({ ...prev, start_time: value }))} />
          </CCol>
          <CCol md={3}>
            <TimeField id="gridEnd" label="Fecho da Escola" value={formData.end_time} onChange={(value) => applyFormData((prev) => ({ ...prev, end_time: value }))} />
          </CCol>
          <CCol md={3}>
            <CFormLabel htmlFor="slotDuration">Duração da Aula</CFormLabel>
            <CInputGroup>
              <CFormInput id="slotDuration" type="number" aria-describedby="slotDuration-unit" value={formData.slot_duration_minutes} onChange={(e) => applyFormData((prev) => ({ ...prev, slot_duration_minutes: e.target.value }))} />
              <CInputGroupText id="slotDuration-unit">Minutos</CInputGroupText>
            </CInputGroup>
          </CCol>
          <CCol md={3}>
            <div className="school-config-break-label">
              <CFormLabel htmlFor="breakDuration">Intervalo</CFormLabel>
              <button
                type="button"
                className="school-config-break-customize"
                aria-label="Personalizar intervalos"
                onClick={() => setBreaksModalOpen(true)}
              >
                <CIcon icon={cilPencil} size="sm" />
              </button>
            </div>
            <CInputGroup>
              <CFormInput id="breakDuration" type="number" aria-describedby="breakDuration-unit" value={formData.break_duration_minutes} onChange={(e) => applyFormData((prev) => ({ ...prev, break_duration_minutes: e.target.value }))} />
              <CInputGroupText id="breakDuration-unit">Minutos</CInputGroupText>
            </CInputGroup>
            {customBreakCount > 0 && (
              <div className="form-text">Pausas personalizadas: {customBreakCount}</div>
            )}
          </CCol>
        </CRow>

        <CRow className="mb-4 align-items-start">
          <CCol md={4}>
            <TimeField id="lunchStart" label="Início do Almoço" value={gridSettings.lunch_window_start} onChange={(value) => setGridSettings({ ...gridSettings, lunch_window_start: value })} />
          </CCol>
          <CCol md={4}>
            <TimeField id="lunchEnd" label="Fim do Almoço" value={gridSettings.lunch_window_end} onChange={(value) => setGridSettings({ ...gridSettings, lunch_window_end: value })} />
          </CCol>
          <CCol md={4}>
            <CFormLabel htmlFor="lunchMin">Duração Mínima Almoço</CFormLabel>
            <CInputGroup>
              <CFormInput id="lunchMin" type="number" aria-describedby="lunchMin-unit" value={gridSettings.lunch_min_duration_minutes} onChange={(e) => setGridSettings({ ...gridSettings, lunch_min_duration_minutes: e.target.value })} />
              <CInputGroupText id="lunchMin-unit">Minutos</CInputGroupText>
            </CInputGroup>
          </CCol>
        </CRow>

        <CRow className="mb-4 align-items-end">
          <CCol md={8}>
            <fieldset className="mb-0">
              <legend className="form-label fw-bold d-block mb-2">Dias de Funcionamento</legend>
              <div className="d-flex gap-2 flex-wrap">
                {DAY_LABELS.map((label, idx) => (
                  <CFormCheck key={label} button={{ color: formData.days[idx] ? 'primary' : 'secondary', variant: formData.days[idx] ? '' : 'outline' }} type="checkbox" id={`day-${idx}`} label={label} checked={formData.days[idx]} onChange={() => toggleDay(idx)} />
                ))}
              </div>
            </fieldset>
          </CCol>
          <CCol md={4} className="d-flex align-items-end justify-content-md-end mt-3 mt-md-0">
            <CButton
              color="primary"
              size="md"
              type="submit"
              disabled={isSubmitting || !orgId}
            >
              <CIcon icon={cilSave} className="me-2" />
              {submitLabel}
            </CButton>
          </CCol>
        </CRow>
      </CForm>

      {preview && (
        <GridChangeImpactPanel
          preview={preview}
          decisions={decisions}
          onDecision={(timeslotId, action) => {
            setDecisions((current) => ({ ...current, [timeslotId]: action }))
          }}
          onPropose={handlePropose}
          isProposing={proposeMutation.isPending}
        />
      )}

      {breaksModalOpen && (
        <BreakTimelineModal
          values={timeslotValues}
          onClose={() => setBreaksModalOpen(false)}
          onApply={(breakOverrides) => {
            applyFormData((prev) => ({ ...prev, break_overrides: breakOverrides }))
            setBreaksModalOpen(false)
          }}
        />
      )}
    </div>
  )
}
