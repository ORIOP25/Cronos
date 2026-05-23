import React, { useState, useEffect } from 'react'
import PageHeader from '../components/PageHeader'
import {
  CCard, CCardBody, CCardHeader, CCol, CRow, CForm, CFormInput,
  CFormCheck, CFormLabel, CButton, CAlert, CBadge,
  CSpinner, CTable, CTableHead, CTableRow, CTableHeaderCell,
  CTableBody, CTableDataCell, CTabs, CTabList, CTab, CTabContent, CTabPanel, CFormSelect,
  CModal, CModalHeader, CModalTitle, CModalBody, CModalFooter
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilSave, cilTrash, cilCloudDownload, cilCalendar } from '@coreui/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import apiClient from '../apiClient'
import { useOrganization } from '@clerk/react'
import { formatDate } from '../utils/formatUtils'
import { TXT, EVENT_TYPE_LABELS } from '../utils/terminology'

const getApiErrorMessage = (error, fallbackMessage) => {
  const detail = error?.response?.data?.detail

  if (typeof detail === 'string' && detail.trim()) {
    return detail
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === 'string') return item
        if (item && typeof item === 'object') {
          return item.msg || item.message || item.detail || ''
        }
        return ''
      })
      .filter(Boolean)

    if (messages.length > 0) {
      return messages.join(' ')
    }
  }

  if (detail && typeof detail === 'object') {
    if (typeof detail.message === 'string' && detail.message.trim()) {
      return detail.message
    }

    if (typeof detail.msg === 'string' && detail.msg.trim()) {
      return detail.msg
    }
  }

  if (typeof error?.message === 'string' && error.message.trim()) {
    return error.message
  }

  return fallbackMessage
}

const CalendarSection = () => {
  const queryClient = useQueryClient()
  const [newEvent, setNewEvent] = useState({
    name: '', start_date: '', end_date: '', event_type: 'school_break',
  })
  const [successMsg, setSuccessMsg] = useState(null)

  const { data: events = [], isLoading } = useQuery({
    queryKey: ['calendar-events'],
    queryFn: async () => {
      const { data } = await apiClient.get('/school/calendar-events/')
      return data
    },
  })

  const syncMutation = useMutation({
    mutationFn: () => apiClient.post('/school/settings/sync-holidays'),
    onSuccess: () => {
      setSuccessMsg(`Feriados nacionais importados com sucesso.`)
      void queryClient.invalidateQueries({ queryKey: ['calendar-events'] })
      setTimeout(() => setSuccessMsg(null), 4000)
    },
  })

  const createMutation = useMutation({
    mutationFn: (payload) => apiClient.post('/school/calendar-events/', payload),
    onSuccess: () => {
      setNewEvent({ name: '', start_date: '', end_date: '', event_type: 'school_break' })
      void queryClient.invalidateQueries({ queryKey: ['calendar-events'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id) => apiClient.delete(`/school/calendar-events/${id}`),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['calendar-events'] }),
  })

  const handleCreate = () => {
    if (!newEvent.name || !newEvent.start_date || !newEvent.end_date) return
    createMutation.mutate(newEvent)
  }

  let eventListContent
  if (isLoading) {
    eventListContent = <div className="text-center py-4"><CSpinner /></div>
  } else if (events.length === 0) {
    eventListContent = (
      <CAlert color="secondary">
        Sem eventos registados. Pode sincronizar os feriados nacionais ou adicionar pausas letivas manualmente.
      </CAlert>
    )
  } else {
    eventListContent = (
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
          {events.map((ev) => (
            <CTableRow key={ev.id}>
              <CTableDataCell>{ev.name}</CTableDataCell>
              <CTableDataCell style={{ whiteSpace: 'nowrap' }}>{formatDate(ev.start_date)}</CTableDataCell>
              <CTableDataCell style={{ whiteSpace: 'nowrap' }}>{formatDate(ev.end_date)}</CTableDataCell>
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
                  onClick={() => { deleteMutation.mutate(ev.id) }}
                >
                  <CIcon icon={cilTrash} />
                </CButton>
              </CTableDataCell>
            </CTableRow>
          ))}
        </CTableBody>
      </CTable>
    )
  }

  return (
    <div>
      {successMsg && <CAlert color="success" className="mb-3">{successMsg}</CAlert>}
      {syncMutation.isError && (
        <CAlert color="danger">
          {getApiErrorMessage(syncMutation.error, 'Erro ao sincronizar feriados.')}
        </CAlert>
      )}
      {createMutation.isError && (
        <CAlert color="danger">
          {getApiErrorMessage(createMutation.error, 'Erro ao adicionar evento. Verifique as datas e tente novamente.')}
        </CAlert>
      )}

      <div className="d-flex align-items-center gap-3 mb-4">
        <CButton
          color="info"
          variant="outline"
          size="sm"
          disabled={syncMutation.isPending}
          onClick={() => { syncMutation.mutate() }}
        >
          <CIcon icon={cilCloudDownload} className="me-1" />
          {syncMutation.isPending ? 'A sincronizar...' : 'Sincronizar Feriados Nacionais'}
        </CButton>
      </div>

      <CCard className="border-0 shadow-sm mb-4">
        <CCardHeader className="bg-white fw-bold py-2">
          <CIcon icon={cilCalendar} className="me-2" />Adicionar Pausa / Evento Manual
        </CCardHeader>
        <CCardBody>
          <CRow className="g-3">
            <CCol md={4}>
              <CFormLabel htmlFor="eventName">Nome do evento</CFormLabel>
              <CFormInput
                id="eventName"
                placeholder="Ex: Férias de Natal"
                value={newEvent.name}
                onChange={(e) => setNewEvent((p) => ({ ...p, name: e.target.value }))}
              />
            </CCol>
            <CCol md={2}>
              <CFormLabel htmlFor="eventStart">Início</CFormLabel>
              <CFormInput
                id="eventStart"
                type="date"
                value={newEvent.start_date}
                onChange={(e) => setNewEvent((p) => ({ ...p, start_date: e.target.value }))}
              />
            </CCol>
            <CCol md={2}>
              <CFormLabel htmlFor="eventEnd">Fim</CFormLabel>
              <CFormInput
                id="eventEnd"
                type="date"
                value={newEvent.end_date}
                onChange={(e) => setNewEvent((p) => ({ ...p, end_date: e.target.value }))}
              />
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
                {TXT.ADD}
              </CButton>
            </CCol>
          </CRow>
        </CCardBody>
      </CCard>

      {eventListContent}
    </div>
  )
}

const SettingsSection = () => {
  const queryClient = useQueryClient()
  const [successMsg, setSuccessMsg] = useState(null)
  const [savePromptMsg, setSavePromptMsg] = useState(null)
  const [saveConfirmationPending, setSaveConfirmationPending] = useState(false)
  const [form, setForm] = useState({
    school_start_date: '',
    school_target_end_date: '',
    school_hard_end_date: '',
    repair_stability_window_days: '14',
  })

  // Soft-Reset state
  const [showResetModal, setShowResetModal] = useState(false)
  const [resetConfirmText, setResetConfirmText] = useState('')
  const [resetChecked, setResetChecked] = useState(false)
  const [resetError, setResetError] = useState('')

  const resetMutation = useMutation({
    mutationFn: (payload) => apiClient.post('/school/settings/soft-reset', payload),
    onSuccess: () => {
      setSuccessMsg('Ano letivo recomeçado com sucesso. Todas as gerações, ocorrências e registos foram apagados.')
      setShowResetModal(false)
      setResetConfirmText('')
      setResetChecked(false)
      window.scrollTo(0, 0)
      setTimeout(() => setSuccessMsg(null), 5000)
    },
    onError: (err) => {
      setResetError(getApiErrorMessage(err, 'Erro ao recomeçar ano letivo.'))
    }
  })

  const handleSoftReset = () => {
    setResetError('')
    if (resetConfirmText !== 'Confirmo' || !resetChecked) return
    resetMutation.mutate({ confirm_phrase: resetConfirmText })
  }

  const { data: settings, isLoading } = useQuery({
    queryKey: ['org-settings'],
    queryFn: async () => {
      const { data } = await apiClient.get('/school/settings/')
      return data
    },
  })

  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (settings && Object.keys(settings).length > 0) {
      setForm({
        school_start_date: settings.school_start_date || '',
        school_target_end_date: settings.school_target_end_date || '',
        school_hard_end_date: settings.school_hard_end_date || '',
        repair_stability_window_days: settings.repair_stability_window_days?.toString() || '14',
      })
    }
  }, [settings])

  useEffect(() => {
    setSaveConfirmationPending(false)
    setSavePromptMsg(null)
  }, [form.school_start_date, form.school_target_end_date, form.school_hard_end_date, form.repair_stability_window_days])
  /* eslint-enable react-hooks/set-state-in-effect */

  const upsertMutation = useMutation({
    mutationFn: (payload) => apiClient.post('/school/settings/', payload),
    onSuccess: () => {
      setSuccessMsg('Período letivo guardado com sucesso.')
      setSavePromptMsg(null)
      setSaveConfirmationPending(false)
      void queryClient.invalidateQueries({ queryKey: ['org-settings'] })
      setTimeout(() => setSuccessMsg(null), 3000)
    },
  })

  const handleSave = () => {
    if (!form.school_start_date || !form.school_target_end_date || !form.school_hard_end_date) {
      setSavePromptMsg('Por favor, preencha todas as datas antes de guardar.')
      setSaveConfirmationPending(false)
      return;
    }

    if (!saveConfirmationPending) {
      setSavePromptMsg('Ao guardar estas definições, o ano letivo em vigor será sobrescrito. Volte a carregar em guardar para confirmar.')
      setSaveConfirmationPending(true)
      return
    }

    const payload = {
      school_start_date: form.school_start_date || null,
      school_target_end_date: form.school_target_end_date || null,
      school_hard_end_date: form.school_hard_end_date || null,
      repair_stability_window_days: form.repair_stability_window_days ? parseInt(form.repair_stability_window_days, 10) : null,
    }
    upsertMutation.mutate(payload)
  }

  if (isLoading) return <div className="d-flex justify-content-center p-5"><CSpinner /></div>

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
            onChange={(e) => setForm({ ...form, school_start_date: e.target.value })}
            text="Data oficial de início do semestre"
          />
        </CCol>
        <CCol md={3}>
          <CFormLabel htmlFor="targetDate" className="school-config-field-label">Data-Alvo Fim</CFormLabel>
          <CFormInput
            id="targetDate"
            type="date"
            value={form.school_target_end_date}
            onChange={(e) => setForm({ ...form, school_target_end_date: e.target.value })}
            text="Data de referência para concluir o planeamento"
          />
        </CCol>
        <CCol md={3}>
          <CFormLabel htmlFor="hardEndDate" className="school-config-field-label">Data limite final</CFormLabel>
          <CFormInput
            id="hardEndDate"
            type="date"
            value={form.school_hard_end_date}
            onChange={(e) => setForm({ ...form, school_hard_end_date: e.target.value })}
            text="Não há aulas após esta data"
          />
        </CCol>
        <CCol md={3}>
          <CFormLabel htmlFor="repairWindow" className="school-config-field-label">Janela de estabilidade (dias)</CFormLabel>
          <CFormInput
            id="repairWindow"
            type="number"
            min={1}
            value={form.repair_stability_window_days}
            onChange={(e) => setForm({ ...form, repair_stability_window_days: e.target.value })}
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
          Recomeçar Ano Letivo
        </CButton>
        <CButton color="primary" onClick={handleSave} disabled={upsertMutation.isPending}>
          <CIcon icon={cilSave} className="me-1" />
          {upsertMutation.isPending ? 'A guardar...' : (saveConfirmationPending ? 'Confirmar guarda' : 'Guardar Configurações Gerais')}
        </CButton>
      </div>

      <CModal visible={showResetModal} onClose={() => { setShowResetModal(false); setResetError(''); setResetConfirmText(''); setResetChecked(false); }} backdrop="static">
        <CModalHeader>
          <CModalTitle className="text-danger fw-bold">Confirmar Ação Destrutiva</CModalTitle>
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
            {resetMutation.isPending ? 'A apagar...' : 'Remover Dados e Recomeçar'}
          </CButton>
        </CModalFooter>
      </CModal>
    </div>
  )
}

const GridSection = () => {
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id
  const [successMsg, setSuccessMsg] = useState(null)
  
  const [formData, setFormData] = useState({
    start_time: '08:00',
    end_time: '18:00',
    slot_duration_minutes: 50,
    break_duration_minutes: 10,
    days: { 0: true, 1: true, 2: true, 3: true, 4: true, 5: false, 6: false },
  })

  const [gridSettings, setGridSettings] = useState({
    lunch_window_start: '12:00',
    lunch_window_end: '14:00',
    lunch_min_duration_minutes: 60,
  })

  useQuery({
    queryKey: ['org-grid-settings'],
    queryFn: async () => {
      const { data } = await apiClient.get('/school/grid-settings/')
      if (data) {
        setGridSettings({
          lunch_window_start: data.lunch_window_start ? data.lunch_window_start.slice(0, 5) : '12:00',
          lunch_window_end: data.lunch_window_end ? data.lunch_window_end.slice(0, 5) : '14:00',
          lunch_min_duration_minutes: data.lunch_min_duration_minutes || 60,
        })
      }
      return data
    },
  })

  const mutation = useMutation({
    mutationFn: (payload) => apiClient.post('/timeslots/generate', payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['timeslots', orgId] })
      void queryClient.invalidateQueries({ queryKey: ['weekSchedule', orgId] })
    },
  })

  const gridSettingsMutation = useMutation({
    mutationFn: (payload) => apiClient.post('/school/grid-settings/', payload),
    onSuccess: () => {
      setSuccessMsg('Grelha configurada com sucesso!')
      void queryClient.invalidateQueries({ queryKey: ['org-grid-settings'] })
      setTimeout(() => setSuccessMsg(null), 3000)
    },
  })

  const handleSubmit = async () => {
    const selectedDays = Object.keys(formData.days)
      .filter((d) => formData.days[d])
      .map((d) => Number.parseInt(d, 10))

    try {
      await gridSettingsMutation.mutateAsync({
        lunch_window_start: gridSettings.lunch_window_start ? `${gridSettings.lunch_window_start}:00` : null,
        lunch_window_end: gridSettings.lunch_window_end ? `${gridSettings.lunch_window_end}:00` : null,
        lunch_min_duration_minutes: Number.parseInt(gridSettings.lunch_min_duration_minutes, 10),
      })

      await mutation.mutateAsync({
        start_time: `${formData.start_time}:00`,
        end_time: `${formData.end_time}:00`,
        slot_duration_minutes: Number.parseInt(formData.slot_duration_minutes, 10),
        break_duration_minutes: Number.parseInt(formData.break_duration_minutes, 10),
        days_of_week: selectedDays,
      })
    } catch {
      // errors handled by React Query
    }
  }

  const toggleDay = (idx) => {
    setFormData((prev) => ({ ...prev, days: { ...prev.days, [idx]: !prev.days[idx] } }))
  }

  const daysLabel = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']

  return (
    <div>
      {successMsg && <CAlert color="success">{successMsg}</CAlert>}
      {(mutation.isError || gridSettingsMutation.isError) && <CAlert color="danger">Erro ao guardar configuração da grelha.</CAlert>}

      <p className="text-muted mb-4">
        Defina aqui o funcionamento geral da escola. Ao guardar, o sistema irá <strong>regenerar todos os blocos horários</strong> base.
      </p>

      <CForm>
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
          <CButton color="primary" size="md" onClick={handleSubmit} disabled={mutation.isPending || gridSettingsMutation.isPending}>
            <CIcon icon={cilSave} className="me-2" />
            {(mutation.isPending || gridSettingsMutation.isPending) ? 'A Processar...' : 'Guardar e Regenerar Grelha'}
          </CButton>
        </div>
      </CForm>
    </div>
  )
}

const SchoolConfig = () => {
  const { organization } = useOrganization()
  const [activeTab, setActiveTab] = useState('settings')

  return (
    <div className="p-4">
      <PageHeader preTitle="Configuração" title="Escola" />

      {organization?.name && (
        <CAlert color="primary" className="d-flex align-items-center gap-2 py-2 mb-4">
          A gerir organização: <CBadge color="light" textColor="primary" className="fs-6">{organization?.name}</CBadge>
        </CAlert>
      )}

      <CTabs activeItemKey={activeTab} onChange={(key) => setActiveTab(key)}>
        <CTabList variant="tabs" className="mb-4">
          <CTab itemKey="settings">Período Letivo</CTab>
          <CTab itemKey="calendar">Calendário e Interrupções</CTab>
          <CTab itemKey="grid">Grelha Horária</CTab>
        </CTabList>

        <CTabContent>
          <CTabPanel itemKey="settings">
          <CCard className="border-0 shadow-sm">
                <CCardHeader className="bg-white fw-bold py-3">Definição do Período Letivo</CCardHeader>
              <CCardBody className="p-4">
                <SettingsSection />
              </CCardBody>
            </CCard>
          </CTabPanel>

          <CTabPanel itemKey="calendar">
          <CCard className="border-0 shadow-sm">
                <CCardHeader className="bg-white fw-bold py-3">Calendário (Feriados e Pausas)</CCardHeader>
              <CCardBody className="p-4">
                <CalendarSection />
              </CCardBody>
            </CCard>
          </CTabPanel>

          <CTabPanel itemKey="grid">
            <CCard className="border-0 shadow-sm">
              <CCardHeader className="bg-white fw-bold py-3">Definição da Grelha Horária</CCardHeader>
              <CCardBody className="p-4">
                <GridSection />
              </CCardBody>
            </CCard>
          </CTabPanel>
        </CTabContent>
      </CTabs>
    </div>
  )
}

export default SchoolConfig
