import { useState } from 'react'
import {
  CCard, CCardBody, CCardHeader, CCol, CRow, CForm, CFormInput,
  CFormCheck, CFormLabel, CButton, CAlert, CBadge, CInputGroup, CInputGroupText,
  CSpinner, CTable, CTableHead, CTableRow, CTableHeaderCell,
  CTableBody, CTableDataCell, CFormSelect,
  CModal, CModalHeader, CModalTitle, CModalBody, CModalFooter
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilSave, cilTrash, cilCalendar } from '@coreui/icons'
import { useOrganization } from '@clerk/react'
import { formatDate } from '../../utils/formatUtils'
import { TXT, EVENT_TYPE_LABELS } from '../../utils/terminology'
import { getApiErrorCode, getApiErrorMessage } from '../../utils/apiErrors'
import {
  timeslotsToGridFormData,
  toGridConfigurationPayload,
  toSchoolSettingsPayload,
} from '../../utils/schoolConfigPayloads'
import { useTransientMessage } from '../../hooks/useTransientMessage'
import FeedbackBanner from '../../components/FeedbackBanner'
import StatePanel from '../../components/StatePanel'
import ConfirmationModal from '../../components/ConfirmationModal'
import PortugueseDateInput from '../../components/PortugueseDateInput'
import { useTimeslots } from '../catalog/data'
import {
  useCalendarEvents,
  useCreateCalendarEvent,
  useDeleteCalendarEvent,
  useGridSettings,
  useRegenerateGrid,
  useSchoolSettings,
  useSoftResetSchoolYear,
  useUpsertSchoolSettings,
} from './data'

export const CalendarSection = () => {
  const [newEvent, setNewEvent] = useState({
    name: '', start_date: '', end_date: '', event_type: 'school_break',
  })
  const { message: successMsg, show: setSuccessMsg } = useTransientMessage()

  const { data: events = [], isLoading } = useCalendarEvents()
  const settingsQuery = useSchoolSettings()
  const settingsMutation = useUpsertSchoolSettings()
  const createMutation = useCreateCalendarEvent()
  const deleteMutation = useDeleteCalendarEvent()
  const [fieldErrors, setFieldErrors] = useState({})
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [automaticHolidaysOverride, setAutomaticHolidaysOverride] = useState(null)
  const automaticHolidaysEnabled = automaticHolidaysOverride ?? Boolean(
    settingsQuery.data?.automatic_holidays_enabled,
  )

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
  else if (sortedEvents.length === 0) eventListContent = <StatePanel state="empty" title="Sem interrupções registadas" description="Ative os feriados automáticos ou adicione uma interrupção manual." compact />
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
      {settingsMutation.isError && (
        <FeedbackBanner tone="danger">
          {getApiErrorMessage(settingsMutation.error, 'Erro ao guardar a preferência de feriados automáticos.')}
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
        </CCardHeader>
        <CCardBody>
          <p className="text-muted mb-3">Registe uma interrupção específica da escola. Os feriados nacionais são sincronizados através da opção automática.</p>
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

      <CCard className="border-0 shadow-sm mb-4">
        <CCardBody>
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
                {
                  onSuccess: () => {
                    setAutomaticHolidaysOverride(null)
                    setSuccessMsg(
                      enabled
                        ? 'Feriados automáticos ativados.'
                        : 'Feriados automáticos desativados. Os eventos existentes foram preservados.',
                    )
                  },
                  onError: () => setAutomaticHolidaysOverride(null),
                },
              )
            }}
          />
          <p className="text-muted small mb-0 mt-2">
            Ativar importa os feriados nacionais e acompanha alterações futuras às datas do período letivo.
          </p>
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
  const { message: resetSuccessMsg, show: showResetSuccess } = useTransientMessage()
  const { message: saveSuccessMsg, show: showSaveSuccess } = useTransientMessage()
  if (isLoading) return <div className="d-flex justify-content-center p-5"><CSpinner /></div>

  const editorKey = `${settings?.school_start_date ?? ''}:${settings?.school_hard_end_date ?? ''}:${settings?.preferred_end_date ?? ''}:${settings?.repair_stability_window_days ?? ''}:${settings?.automatic_holidays_enabled ?? ''}`
  return (
    <>
      {resetSuccessMsg && <CAlert color="success" className="mb-3">{resetSuccessMsg}</CAlert>}
      {saveSuccessMsg && <CAlert color="success" className="mb-3">{saveSuccessMsg}</CAlert>}
      <SettingsEditor key={editorKey} settings={settings} onSoftResetSuccess={showResetSuccess} onSaveSuccess={showSaveSuccess} />
    </>
  )
}

const SettingsEditor = ({ settings, onSoftResetSuccess, onSaveSuccess }) => {
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
        onSoftResetSuccess('Ano letivo recomeçado com sucesso. Todas as gerações, ocorrências e registos foram apagados.', 10_000)
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
    const validationMessage = validateSettingsForm(form)
    if (validationMessage) {
      setSavePromptMsg(validationMessage)
      return
    }
    setShowSaveModal(true)
  }

  const confirmSave = () => {
    upsertMutation.mutate(toSchoolSettingsPayload(form), {
      onSuccess: () => {
        onSaveSuccess('Período letivo guardado com sucesso.')
        setSavePromptMsg(null)
        setShowSaveModal(false)
      },
      onError: () => setShowSaveModal(false),
    })
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
      {
        onSuccess: () => {
          setForm((current) => ({ ...current, automatic_holidays_enabled: false }))
          onSaveSuccess('Período letivo guardado com os feriados automáticos desativados.')
          setSavePromptMsg(null)
        },
      },
    )
  }

  return (
    <div>
      {savePromptMsg && <CAlert color="warning" className="mb-3">{savePromptMsg}</CAlert>}
      {upsertMutation.isError && (
        <CAlert color="danger">
          <div className="d-flex flex-wrap align-items-center gap-2">
            <span>{getApiErrorMessage(upsertMutation.error, 'Erro ao guardar configuração.')}</span>
            {canDisableAutomaticHolidays && (
              <CButton
                color="link"
                className="p-0"
                onClick={handleDisableAutomaticHolidays}
                disabled={upsertMutation.isPending}
              >
                Desativar feriados automáticos e guardar
              </CButton>
            )}
          </div>
        </CAlert>
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
            text="Alvo do gerador; tem de ficar antes da data limite"
          />
        </CCol>
        <CCol md={3}>
          <CFormLabel htmlFor="repairWindow" className="school-config-field-label">Janela de estabilidade</CFormLabel>
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
          <div id="repairWindow-help" className="form-text">Período em que se evita refazer horários</div>
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
            <CFormLabel htmlFor="slotDuration">Duração da Aula</CFormLabel>
            <CInputGroup>
              <CFormInput id="slotDuration" type="number" aria-describedby="slotDuration-unit" value={formData.slot_duration_minutes} onChange={(e) => setFormData({ ...formData, slot_duration_minutes: e.target.value })} />
              <CInputGroupText id="slotDuration-unit">Minutos</CInputGroupText>
            </CInputGroup>
          </CCol>
          <CCol md={3}>
            <CFormLabel htmlFor="breakDuration">Intervalo</CFormLabel>
            <CInputGroup>
              <CFormInput id="breakDuration" type="number" aria-describedby="breakDuration-unit" value={formData.break_duration_minutes} onChange={(e) => setFormData({ ...formData, break_duration_minutes: e.target.value })} />
              <CInputGroupText id="breakDuration-unit">Minutos</CInputGroupText>
            </CInputGroup>
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
                {daysLabel.map((label, idx) => (
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
              disabled={mutation.isPending || !orgId}
            >
              <CIcon icon={cilSave} className="me-2" />
              {mutation.isPending ? 'A regenerar' : 'Guardar e regenerar grelha'}
            </CButton>
          </CCol>
        </CRow>
      </CForm>
    </div>
  )
}
