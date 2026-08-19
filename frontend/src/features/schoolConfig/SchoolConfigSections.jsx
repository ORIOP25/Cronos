import { useState } from 'react'
import {
  CCard, CCardBody, CCardHeader, CCol, CRow, CForm, CFormInput,
  CFormCheck, CFormLabel, CButton, CAlert, CBadge,
  CSpinner, CTable, CTableHead, CTableRow, CTableHeaderCell,
  CTableBody, CTableDataCell, CFormSelect,
  CModal, CModalHeader, CModalTitle, CModalBody, CModalFooter
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilSave, cilTrash, cilCloudDownload, cilCalendar } from '@coreui/icons'
import { useOrganization } from '@clerk/react'
import { formatDate } from '../../utils/formatUtils'
import { TXT, EVENT_TYPE_LABELS } from '../../utils/terminology'
import { getApiErrorMessage } from '../../utils/apiErrors'
import {
  timeslotsToGridFormData,
  toGridConfigurationPayload,
  toSchoolSettingsPayload,
} from '../../utils/schoolConfigPayloads'
import { useTransientMessage } from '../../hooks/useTransientMessage'
import FeedbackBanner from '../../components/FeedbackBanner'
import StatePanel from '../../components/StatePanel'
import ConfirmationModal from '../../components/ConfirmationModal'
import { useTimeslots } from '../catalog/data'
import {
  useCalendarEvents,
  useCreateCalendarEvent,
  useDeleteCalendarEvent,
  useGridSettings,
  useRegenerateGrid,
  useSchoolSettings,
  useSoftResetSchoolYear,
  useSyncHolidays,
  useUpsertSchoolSettings,
} from './data'

export const CalendarSection = () => {
  const [newEvent, setNewEvent] = useState({
    name: '', start_date: '', end_date: '', event_type: 'school_break',
  })
  const { message: successMsg, show: setSuccessMsg } = useTransientMessage()

  const { data: events = [], isLoading } = useCalendarEvents()
  const syncMutation = useSyncHolidays()
  const createMutation = useCreateCalendarEvent()
  const deleteMutation = useDeleteCalendarEvent()
  const [fieldErrors, setFieldErrors] = useState({})
  const [deleteTarget, setDeleteTarget] = useState(null)

  const handleCreate = () => {
    const errors = {}
    if (!newEvent.name.trim()) errors.name = 'Indique o nome do evento.'
    if (!newEvent.start_date) errors.start_date = 'Indique a data de início.'
    if (!newEvent.end_date) errors.end_date = 'Indique a data de fim.'
    if (newEvent.start_date && newEvent.end_date && newEvent.end_date < newEvent.start_date) errors.end_date = 'A data de fim deve ser posterior ou igual à data de início.'
    setFieldErrors(errors)
    if (Object.keys(errors).length) return
    createMutation.mutate(newEvent, {
      onSuccess: () => { setNewEvent({ name: '', start_date: '', end_date: '', event_type: 'school_break' }); setFieldErrors({}); setSuccessMsg('Evento adicionado com sucesso.') },
    })
  }

  const sortedEvents = [...events].sort((left, right) => left.start_date.localeCompare(right.start_date))
  let eventListContent
  if (isLoading) eventListContent = <StatePanel state="loading" title="A carregar eventos" compact />
  else if (sortedEvents.length === 0) eventListContent = <StatePanel state="empty" title="Sem interrupções registadas" description="Importe feriados nacionais ou adicione uma interrupção manual." compact />
  else eventListContent = (
      <CTable striped hover responsive>
        <CTableHead>
          <CTableRow>
            <CTableHeaderCell>Nome</CTableHeaderCell>
            <CTableHeaderCell>Início</CTableHeaderCell>
            <CTableHeaderCell>Fim</CTableHeaderCell>
            <CTableHeaderCell>Tipo</CTableHeaderCell>
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
                <CBadge color={ev.source === 'auto' ? 'info' : 'secondary'}>
                  {ev.source === 'auto' ? 'Automático' : 'Manual'}
                </CBadge>
              </CTableDataCell>
              <CTableDataCell>
                <CButton
                  color="danger"
                  variant="ghost"
                  size="sm"
                  disabled={deleteMutation.isPending}
                  aria-label={`Eliminar ${ev.name}`}
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

  return (
    <div>
      {successMsg && <div className="mb-3"><FeedbackBanner tone="success">{successMsg}</FeedbackBanner></div>}
      {syncMutation.isError && (
        <FeedbackBanner tone="danger">
          {getApiErrorMessage(syncMutation.error, 'Erro ao sincronizar feriados.')}
        </FeedbackBanner>
      )}
      {createMutation.isError && (
        <FeedbackBanner tone="danger">
          {getApiErrorMessage(createMutation.error, 'Erro ao adicionar evento. Verifique as datas e tente novamente.')}
        </FeedbackBanner>
      )}

      <CCard className="border-0 shadow-sm mb-4 calendar-event-editor">
        <CCardHeader className="bg-white fw-bold py-2 calendar-event-editor__header">
          <span><CIcon icon={cilCalendar} className="me-2" />Adicionar Evento</span>
          <CButton
            color="secondary"
            variant="outline"
            size="sm"
            className="calendar-import-action"
            aria-label="Importar feriados nacionais"
            title="Importar os feriados nacionais que ainda não estão no calendário"
            disabled={syncMutation.isPending}
            onClick={() => syncMutation.mutate(undefined, {
              onSuccess: (result) => setSuccessMsg(result?.imported_count === 0 ? 'Não foram encontrados novos feriados.' : result?.imported_count === 1 ? '1 feriado importado.' : `${result?.imported_count ?? 0} feriados importados.`),
            })}
          >
            <CIcon icon={cilCloudDownload} className="me-1" />
            {syncMutation.isPending ? 'A Importar' : 'Importar Feriados'}
          </CButton>
        </CCardHeader>
        <CCardBody>
          <p className="text-muted mb-3">Registe uma interrupção específica da escola ou importe os feriados nacionais.</p>
          <CRow className="g-3">
            <CCol md={4}>
              <CFormLabel htmlFor="eventName">Nome do evento</CFormLabel>
              <CFormInput
                id="eventName"
                placeholder="Ex: Férias de Natal"
                value={newEvent.name}
                onChange={(e) => setNewEvent((p) => ({ ...p, name: e.target.value }))}
                invalid={Boolean(fieldErrors.name)}
              />
              {fieldErrors.name && <div className="text-danger small mt-1">{fieldErrors.name}</div>}
            </CCol>
            <CCol md={2}>
              <CFormLabel htmlFor="eventStart">Início</CFormLabel>
              <CFormInput
                id="eventStart"
                type="date"
                value={newEvent.start_date}
                onChange={(e) => setNewEvent((p) => ({ ...p, start_date: e.target.value }))}
                invalid={Boolean(fieldErrors.start_date)}
              />
              {fieldErrors.start_date && <div className="text-danger small mt-1">{fieldErrors.start_date}</div>}
            </CCol>
            <CCol md={2}>
              <CFormLabel htmlFor="eventEnd">Fim</CFormLabel>
              <CFormInput
                id="eventEnd"
                type="date"
                value={newEvent.end_date}
                onChange={(e) => setNewEvent((p) => ({ ...p, end_date: e.target.value }))}
                invalid={Boolean(fieldErrors.end_date)}
              />
              {fieldErrors.end_date && <div className="text-danger small mt-1">{fieldErrors.end_date}</div>}
            </CCol>
            <CCol md={3}>
              <CFormLabel htmlFor="eventType">Tipo</CFormLabel>
              <CFormSelect
                id="eventType"
                value={newEvent.event_type}
                onChange={(e) => setNewEvent((p) => ({ ...p, event_type: e.target.value }))}
              >
                <option value="school_break">Pausa Escolar</option>
                <option value="exam_period">Período de Exames</option>
                <option value="other">Outro</option>
              </CFormSelect>
            </CCol>
            <CCol md={1} className="d-flex align-items-end">
              <CButton color="primary" onClick={handleCreate} disabled={createMutation.isPending}>
                {createMutation.isPending ? 'A adicionar' : 'Adicionar evento'}
              </CButton>
            </CCol>
          </CRow>
        </CCardBody>
      </CCard>

      {eventListContent}
      <ConfirmationModal
        visible={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => { deleteMutation.mutate(deleteTarget.id, { onSuccess: () => setDeleteTarget(null) }) }}
        title="Eliminar evento"
        message={deleteTarget ? `O evento “${deleteTarget.name}” será eliminado. Esta ação não pode ser desfeita.` : ''}
        confirmText="Eliminar evento"
        isLoading={deleteMutation.isPending}
      />
    </div>
  )
}
function toSettingsForm(settings) {
  return {
    school_start_date: settings?.school_start_date || '',
    school_hard_end_date: settings?.school_hard_end_date || '',
    repair_stability_window_days: settings?.repair_stability_window_days?.toString() || '14',
  }
}

export const SettingsSection = () => {
  const { data: settings, isLoading } = useSchoolSettings()
  if (isLoading) return <div className="d-flex justify-content-center p-5"><CSpinner /></div>

  const editorKey = `${settings?.school_start_date ?? ''}:${settings?.school_hard_end_date ?? ''}:${settings?.repair_stability_window_days ?? ''}`
  return <SettingsEditor key={editorKey} settings={settings} />
}

const SettingsEditor = ({ settings }) => {
  const { message: successMsg, show: setSuccessMsg } = useTransientMessage()
  const [savePromptMsg, setSavePromptMsg] = useState(null)
  const [showSaveModal, setShowSaveModal] = useState(false)
  const [form, setForm] = useState(() => toSettingsForm(settings))

  // Soft-Reset state
  const [showResetModal, setShowResetModal] = useState(false)
  const [resetConfirmText, setResetConfirmText] = useState('')
  const [resetChecked, setResetChecked] = useState(false)
  const [resetError, setResetError] = useState('')

  const resetMutation = useSoftResetSchoolYear()

  const handleSoftReset = () => {
    setResetError('')
    if (resetConfirmText !== 'Confirmo' || !resetChecked) return
    resetMutation.mutate({ confirm_phrase: resetConfirmText }, {
      onSuccess: () => {
        setSuccessMsg('Ano letivo recomeçado com sucesso. Todas as gerações, ocorrências e registos foram apagados.')
        setShowResetModal(false)
        setResetConfirmText('')
        setResetChecked(false)
        window.scrollTo(0, 0)
      },
      onError: (err) => {
        setResetError(getApiErrorMessage(err, 'Erro ao recomeçar ano letivo.'))
      },
    })
  }

  const updateForm = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }))
    setSavePromptMsg(null)
  }

  const upsertMutation = useUpsertSchoolSettings()

  const handleSave = () => {
    if (!form.school_start_date || !form.school_hard_end_date) {
      setSavePromptMsg('Por favor, preencha todas as datas antes de guardar.')
      return;
    }
    if (form.school_hard_end_date <= form.school_start_date) {
      setSavePromptMsg('A data-limite deve ser posterior à data de início.')
      return
    }
    setShowSaveModal(true)
  }

  const confirmSave = () => {
    upsertMutation.mutate(toSchoolSettingsPayload(form), {
      onSuccess: () => {
        setSuccessMsg('Período letivo guardado com sucesso.')
        setSavePromptMsg(null)
        setShowSaveModal(false)
      },
    })
  }

  return (
    <div>
      {successMsg && <CAlert color="success" className="mb-3">{successMsg}</CAlert>}
      {savePromptMsg && <CAlert color="warning" className="mb-3">{savePromptMsg}</CAlert>}
      {upsertMutation.isError && (
        <CAlert color="danger">
          {getApiErrorMessage(upsertMutation.error, 'Erro ao guardar configuração.')}
        </CAlert>
      )}
      
      <CRow className="g-3 mb-3 align-items-start">
        <CCol md={3}>
          <CFormLabel htmlFor="startDate" className="school-config-field-label">Início das Aulas</CFormLabel>
          <CFormInput
            id="startDate"
            type="date"
            value={form.school_start_date}
            onChange={(e) => updateForm('school_start_date', e.target.value)}
            text="Data oficial de início do semestre"
          />
        </CCol>
        <CCol md={3}>
          <CFormLabel htmlFor="hardEndDate" className="school-config-field-label">Data limite final</CFormLabel>
          <CFormInput
            id="hardEndDate"
            type="date"
            value={form.school_hard_end_date}
            onChange={(e) => updateForm('school_hard_end_date', e.target.value)}
            text="Não há aulas após esta data"
          />
        </CCol>
        <CCol md={3}>
          <CFormLabel htmlFor="repairWindow" className="school-config-field-label">Janela de estabilidade (dias)</CFormLabel>
          <CFormInput
            id="repairWindow"
            type="number"
            min={0}
            value={form.repair_stability_window_days}
            onChange={(e) => updateForm('repair_stability_window_days', e.target.value)}
            text="Período em que se evita refazer horários"
          />
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
           {upsertMutation.isPending ? 'A guardar' : 'Guardar alterações'}
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
          <CAlert color="warning">
              Esta ação não pode ser desfeita. Todos os dados do ano letivo anterior, incluindo horários, ocorrências e registos de aulas, serão removidos permanentemente.
            </CAlert>
          
          {resetError && <CAlert color="danger">{resetError}</CAlert>}

          <div className="mb-3 mt-4">
            <CFormCheck 
              id="resetCheck"
              label="Compreendo que irei apagar todos os horários e registos."
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
            {resetMutation.isPending ? 'A remover dados' : 'Remover dados e recomeçar'}
          </CButton>
        </CModalFooter>
      </CModal>
    </div>
  )
}

export const GridSection = () => {
  const orgId = useOrganization().organization?.id
  const settingsQuery = useGridSettings()
  const timeslotsQuery = useTimeslots()

  if (settingsQuery.isLoading || timeslotsQuery.isLoading) {
    return <div className="school-config-skeleton" aria-busy="true"><span className="skeleton" /><span className="skeleton" /><span className="skeleton" /><span className="skeleton" /></div>
  }
  const queryError = settingsQuery.error || timeslotsQuery.error
  if (queryError) {
    return <CAlert color="danger">{getApiErrorMessage(queryError, 'Erro ao carregar a grelha.')}</CAlert>
  }

  let initialFormData
  try {
    initialFormData = timeslotsToGridFormData(timeslotsQuery.data)
  } catch (error) {
    return (
      <div>
        <CAlert color="danger">{error.message}</CAlert>
        <CButton color="primary" disabled>Guardar e Regenerar Grelha</CButton>
      </div>
    )
  }
  const data = settingsQuery.data
  const initialGridSettings = {
    lunch_window_start: data?.lunch_window_start?.slice(0, 5) || '12:00',
    lunch_window_end: data?.lunch_window_end?.slice(0, 5) || '14:00',
    lunch_min_duration_minutes: data?.lunch_min_duration_minutes ?? 60,
  }

  return (
    <GridEditor
      key={orgId}
      orgId={orgId}
      initialFormData={initialFormData}
      initialGridSettings={initialGridSettings}
    />
  )
}

const GridEditor = ({ orgId, initialFormData, initialGridSettings }) => {
  const { message: feedback, show: showFeedback, clear: clearFeedback } = useTransientMessage()
  const [formData, setFormData] = useState(initialFormData)
  const [gridSettings, setGridSettings] = useState(initialGridSettings)

  const mutation = useRegenerateGrid()

  const validateForm = () => {
    const duration = Number(formData.slot_duration_minutes)
    const breakDuration = Number(formData.break_duration_minutes)
    const lunchDuration = Number(gridSettings.lunch_min_duration_minutes)
    const toMinutes = (value) => {
      const [hours, minutes] = String(value || '').split(':').map(Number)
      return Number.isFinite(hours) && Number.isFinite(minutes) ? hours * 60 + minutes : NaN
    }
    const lunchStart = toMinutes(gridSettings.lunch_window_start)
    const lunchEnd = toMinutes(gridSettings.lunch_window_end)
    if (
      !formData.start_time
      || !formData.end_time
      || !gridSettings.lunch_window_start
      || !gridSettings.lunch_window_end
      || !Number.isFinite(duration)
      || duration <= 0
      || !Number.isFinite(breakDuration)
      || breakDuration < 0
      || !Number.isFinite(lunchDuration)
      || lunchDuration <= 0
      || !Number.isFinite(lunchStart)
      || !Number.isFinite(lunchEnd)
      || lunchEnd <= lunchStart
      || formData.end_time <= formData.start_time
      || !Object.values(formData.days).some(Boolean)
    ) {
      return 'Preencha uma grelha válida, com pelo menos um dia de funcionamento.'
    }
    if (lunchDuration > lunchEnd - lunchStart) return 'A duração mínima do almoço não pode exceder a janela configurada.'
    return null
  }

  const handleSubmit = (event) => {
    event.preventDefault()
    clearFeedback()
    mutation.reset()
    const validationError = validateForm()
    if (validationError) {
      showFeedback({ color: 'danger', message: validationError }, 6000)
      return
    }
    mutation.mutate(toGridConfigurationPayload({ formData, gridSettings }), {
      onSuccess: (payload) => {
        showFeedback({ color: 'success', message: payload.message })
      },
      onError: (error) => {
        showFeedback({
          color: 'danger',
          message: getApiErrorMessage(error, 'Erro ao guardar configuração da grelha.'),
        }, 6000)
      },
    })
  }

  const toggleDay = (idx) => {
    setFormData((prev) => ({ ...prev, days: { ...prev.days, [idx]: !prev.days[idx] } }))
  }

  const daysLabel = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']

  return (
    <div>
      {feedback && <CAlert color={feedback.color}>{feedback.message}</CAlert>}

      <p className="text-muted mb-4">
        Defina aqui o funcionamento geral da escola. Ao guardar, o sistema irá <strong>regenerar todos os blocos horários</strong> base.
      </p>

      <CForm onSubmit={handleSubmit}>
        <CRow className="mb-4 align-items-start">
          <CCol md={3}>
            <CFormInput id="gridStart" type="time" label="Abertura da Escola" value={formData.start_time} onChange={(e) => setFormData({ ...formData, start_time: e.target.value })} />
          </CCol>
          <CCol md={3}>
            <CFormInput id="gridEnd" type="time" label="Fecho da Escola" value={formData.end_time} onChange={(e) => setFormData({ ...formData, end_time: e.target.value })} />
          </CCol>
          <CCol md={3}>
            <CFormInput id="slotDuration" type="number" label="Duração da Aula (min)" value={formData.slot_duration_minutes} onChange={(e) => setFormData({ ...formData, slot_duration_minutes: e.target.value })} />
          </CCol>
          <CCol md={3}>
            <CFormInput id="breakDuration" type="number" label="Intervalo (min)" value={formData.break_duration_minutes} onChange={(e) => setFormData({ ...formData, break_duration_minutes: e.target.value })} />
          </CCol>
        </CRow>

        <CRow className="mb-4 align-items-start">
          <CCol md={4}>
            <CFormInput id="lunchStart" type="time" label="Início do Almoço" value={gridSettings.lunch_window_start} onChange={(e) => setGridSettings({ ...gridSettings, lunch_window_start: e.target.value })} />
          </CCol>
          <CCol md={4}>
            <CFormInput id="lunchEnd" type="time" label="Fim do Almoço" value={gridSettings.lunch_window_end} onChange={(e) => setGridSettings({ ...gridSettings, lunch_window_end: e.target.value })} />
          </CCol>
          <CCol md={4}>
            <CFormInput id="lunchMin" type="number" label="Duração Mínima Almoço (min)" value={gridSettings.lunch_min_duration_minutes} onChange={(e) => setGridSettings({ ...gridSettings, lunch_min_duration_minutes: e.target.value })} />
          </CCol>
        </CRow>

        <fieldset className="mb-4">
          <legend className="form-label fw-bold d-block mb-2">Dias de Funcionamento</legend>
          <div className="d-flex gap-2 flex-wrap">
            {daysLabel.map((label, idx) => (
              <CFormCheck key={label} button={{ color: formData.days[idx] ? 'primary' : 'secondary', variant: formData.days[idx] ? '' : 'outline' }} type="checkbox" id={`day-${idx}`} label={label} checked={formData.days[idx]} onChange={() => toggleDay(idx)} />
            ))}
          </div>
        </fieldset>

        <div className="d-grid gap-2 d-md-flex justify-content-md-end">
          <CButton
            color="primary"
            size="md"
            type="submit"
            disabled={mutation.isPending || !orgId}
          >
            <CIcon icon={cilSave} className="me-2" />
             {mutation.isPending ? 'A regenerar' : 'Guardar e regenerar grelha'}
          </CButton>
        </div>
      </CForm>
    </div>
  )
}
