import React, { useState, useEffect } from 'react'
import PropTypes from 'prop-types'
import {
  CCard, CCardBody, CCardHeader, CCol, CRow, CForm, CFormInput,
  CFormCheck, CFormSelect, CFormLabel, CButton, CAlert, CBadge,
  CSpinner, CTable, CTableHead, CTableRow, CTableHeaderCell,
  CTableBody, CTableDataCell, CTabs, CTabList, CTab, CTabContent, CTabPanel,
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilSettings, cilSave, cilTrash, cilCloudDownload, cilCalendar } from '@coreui/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import apiClient from '../apiClient'
import { useAuthStore } from '../store'

// ==========================================
//  SECÇÃO 1 — Calendário Escolar
// ==========================================

const EVENT_TYPE_LABELS = {
  national_holiday: 'Feriado Nacional',
  school_break: 'Pausa Escolar',
  exam_period: 'Período de Exames',
  other: 'Outro',
}

const REGION_CODE_LABELS = {
  '01': 'Aveiro',
  '1': 'Aveiro',
  '02': 'Beja',
  '2': 'Beja',
  '03': 'Braga',
  '3': 'Braga',
  '04': 'Braganca',
  '4': 'Braganca',
  '05': 'Castelo Branco',
  '5': 'Castelo Branco',
  '06': 'Coimbra',
  '6': 'Coimbra',
  '07': 'Evora',
  '7': 'Evora',
  '08': 'Faro',
  '8': 'Faro',
  '09': 'Guarda',
  '9': 'Guarda',
  '10': 'Leiria',
  '11': 'Lisboa',
  '12': 'Portalegre',
  '13': 'Porto',
  '14': 'Santarem',
  '15': 'Setubal',
  '16': 'Viana do Castelo',
  '17': 'Vila Real',
  '18': 'Viseu',
  '20': 'Regiao Autonoma dos Acores',
  '30': 'Regiao Autonoma da Madeira',
}

const formatRegionLabel = (code) => {
  if (!code) return '—'
  const label = REGION_CODE_LABELS[code]
  if (label) return `${label} (${code})`
  return `Regiao ${code}`
}

const CalendarSection = ({ academicYears }) => {
  const queryClient = useQueryClient()
  const [selectedYear, setSelectedYear] = useState(academicYears[0] ?? '')
  const [newEvent, setNewEvent] = useState({
    name: '', start_date: '', end_date: '', event_type: 'school_break',
  })
  const [successMsg, setSuccessMsg] = useState(null)

  const { data: events = [], isLoading } = useQuery({
    queryKey: ['calendar-events', selectedYear],
    queryFn: async () => {
      const { data } = await apiClient.get(
        `/school/calendar-events/?academic_year=${selectedYear}`,
      )
      return data
    },
    enabled: !!selectedYear,
  })

  const syncMutation = useMutation({
    mutationFn: () => apiClient.post(`/school/settings/${selectedYear}/sync-holidays`),
    onSuccess: (res) => {
      setSuccessMsg(`${res.data.imported_count} feriados importados para ${selectedYear}.`)
      void queryClient.invalidateQueries({ queryKey: ['calendar-events', selectedYear] })
      setTimeout(() => setSuccessMsg(null), 4000)
    },
  })

  const createMutation = useMutation({
    mutationFn: (payload) => apiClient.post('/school/calendar-events/', payload),
    onSuccess: () => {
      setNewEvent({ name: '', start_date: '', end_date: '', event_type: 'school_break' })
      void queryClient.invalidateQueries({ queryKey: ['calendar-events', selectedYear] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id) => apiClient.delete(`/school/calendar-events/${id}`),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['calendar-events', selectedYear] }),
  })

  const handleCreate = () => {
    if (!newEvent.name || !newEvent.start_date || !newEvent.end_date) return
    createMutation.mutate({ ...newEvent, academic_year: selectedYear })
  }

  let eventListContent
  if (isLoading) {
    eventListContent = <div className="text-center py-4"><CSpinner /></div>
  } else if (events.length === 0) {
    eventListContent = (
      <CAlert color="secondary">
        Sem eventos para {selectedYear}. Sincronize os feriados ou adicione pausas manualmente.
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
              <CTableDataCell>{ev.start_date}</CTableDataCell>
              <CTableDataCell>{ev.end_date}</CTableDataCell>
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
      {syncMutation.isError && <CAlert color="danger">Erro ao sincronizar feriados.</CAlert>}

      <div className="d-flex align-items-center gap-3 mb-4">
        <CFormLabel htmlFor="yearSelectCalendar" className="mb-0 fw-bold">Ano letivo:</CFormLabel>
        <CFormSelect
          id="yearSelectCalendar"
          value={selectedYear}
          onChange={(e) => setSelectedYear(e.target.value)}
          style={{ width: 160 }}
        >
          {academicYears.map((y) => (
            <option key={y} value={y}>{y}</option>
          ))}
        </CFormSelect>
        <CButton
          color="info"
          variant="outline"
          size="sm"
          disabled={!selectedYear || syncMutation.isPending}
          onClick={() => { syncMutation.mutate() }}
        >
          <CIcon icon={cilCloudDownload} className="me-1" />
          {syncMutation.isPending ? 'A sincronizar...' : 'Sincronizar Feriados Nacionais'}
        </CButton>
      </div>

      {/* Formulário novo evento */}
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
              <CButton
                color="primary"
                onClick={handleCreate}
                disabled={createMutation.isPending}
              >
                +
              </CButton>
            </CCol>
          </CRow>
        </CCardBody>
      </CCard>

      {/* Lista de eventos */}
      {eventListContent}
    </div>
  )
}

CalendarSection.propTypes = {
  academicYears: PropTypes.arrayOf(PropTypes.string).isRequired,
}

// ==========================================
//  SECÇÃO 2 — Configurações do Ano Letivo
// ==========================================

const SettingsSection = ({ regions, onYearsChange }) => {
  const queryClient = useQueryClient()
  const [successMsg, setSuccessMsg] = useState(null)
  const [form, setForm] = useState({
    academic_year: '',
    school_start_date: '',
    school_target_end_date: '',
    school_hard_end_date: '',
    region_code: '',
    lunch_window_start: '',
    lunch_window_end: '',
    lunch_min_duration_minutes: '60',
  })

  const { data: settingsList = [], isLoading } = useQuery({
    queryKey: ['org-settings'],
    queryFn: async () => {
      const { data } = await apiClient.get('/school/settings/')
      return data
    },
  })

  // React Query v5: onSuccess removido — usar useEffect para efeitos laterais
  useEffect(() => {
    const years = settingsList.map((s) => s.academic_year)
    onYearsChange(years)
  }, [settingsList, onYearsChange])

  const upsertMutation = useMutation({
    mutationFn: (payload) => apiClient.post('/school/settings/', payload),
    onSuccess: () => {
      setSuccessMsg('Configuração guardada com sucesso.')
      setForm({
        academic_year: '',
        school_start_date: '',
        school_target_end_date: '',
        school_hard_end_date: '',
        region_code: '',
        lunch_window_start: '',
        lunch_window_end: '',
        lunch_min_duration_minutes: '60',
      })
      void queryClient.invalidateQueries({ queryKey: ['org-settings'] })
      setTimeout(() => setSuccessMsg(null), 3000)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (year) => apiClient.delete(`/school/settings/${year}`),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['org-settings'] }),
  })

  const handleSave = () => {
    if (!form.academic_year) return
    const payload = {
      academic_year: form.academic_year,
      school_start_date: form.school_start_date || null,
      school_target_end_date: form.school_target_end_date || null,
      school_hard_end_date: form.school_hard_end_date || null,
      region_code: form.region_code || null,
      lunch_window_start: form.lunch_window_start || null,
      lunch_window_end: form.lunch_window_end || null,
      lunch_min_duration_minutes: form.lunch_min_duration_minutes
        ? Number.parseInt(form.lunch_min_duration_minutes, 10)
        : null,
    }
    upsertMutation.mutate(payload)
  }

  let settingsListContent
  if (isLoading) {
    settingsListContent = <div className="text-center py-4"><CSpinner /></div>
  } else if (settingsList.length === 0) {
    settingsListContent = <CAlert color="secondary">Sem anos letivos configurados. Adicione um acima.</CAlert>
  } else {
    settingsListContent = (
      <CTable striped hover responsive>
        <CTableHead>
          <CTableRow>
            <CTableHeaderCell>Ano Letivo</CTableHeaderCell>
            <CTableHeaderCell>Início das Aulas</CTableHeaderCell>
            <CTableHeaderCell>Data-Alvo Fim</CTableHeaderCell>
            <CTableHeaderCell>Limite Rígido</CTableHeaderCell>
            <CTableHeaderCell>Região</CTableHeaderCell>
            <CTableHeaderCell>Janela de Almoço</CTableHeaderCell>
            <CTableHeaderCell />
          </CTableRow>
        </CTableHead>
        <CTableBody>
          {settingsList.map((s) => (
            <CTableRow key={s.id}>
              <CTableDataCell><CBadge color="primary">{s.academic_year}</CBadge></CTableDataCell>
              <CTableDataCell>{s.school_start_date ?? '—'}</CTableDataCell>
              <CTableDataCell>{s.school_target_end_date ?? '—'}</CTableDataCell>
              <CTableDataCell>{s.school_hard_end_date ?? '—'}</CTableDataCell>
              <CTableDataCell>{formatRegionLabel(s.region_code)}</CTableDataCell>
              <CTableDataCell>
                {s.lunch_window_start && s.lunch_window_end
                  ? `${s.lunch_window_start.slice(0, 5)}-${s.lunch_window_end.slice(0, 5)} (${s.lunch_min_duration_minutes ?? 0} min)`
                  : '—'}
              </CTableDataCell>
              <CTableDataCell>
                <CButton
                  color="danger"
                  variant="ghost"
                  size="sm"
                  disabled={deleteMutation.isPending}
                  onClick={() => { deleteMutation.mutate(s.academic_year) }}
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
      {upsertMutation.isError && <CAlert color="danger">Erro ao guardar configuração.</CAlert>}

      <CCard className="border-0 shadow-sm mb-4">
        <CCardHeader className="bg-white fw-bold py-2">Adicionar / Atualizar Ano Letivo</CCardHeader>
        <CCardBody>
          <p className="text-muted small mb-3">
            Pode existir um registo por ano letivo. A chave é o campo <strong>Ano Letivo</strong>.
            Se já existir, os valores são atualizados.
          </p>
          <CRow className="g-3">
            <CCol md={2}>
              <CFormLabel htmlFor="acYear">Ano Letivo *</CFormLabel>
              <CFormInput
                id="acYear"
                placeholder="2025/2026"
                value={form.academic_year}
                onChange={(e) => setForm((p) => ({ ...p, academic_year: e.target.value }))}
              />
            </CCol>
            <CCol md={2}>
              <CFormLabel htmlFor="startDate">Início das Aulas</CFormLabel>
              <CFormInput
                id="startDate"
                type="date"
                value={form.school_start_date}
                onChange={(e) => setForm((p) => ({ ...p, school_start_date: e.target.value }))}
              />
            </CCol>
            <CCol md={2}>
              <CFormLabel htmlFor="targetDate">Data-Alvo Fim</CFormLabel>
              <CFormInput
                id="targetDate"
                type="date"
                value={form.school_target_end_date}
                onChange={(e) => setForm((p) => ({ ...p, school_target_end_date: e.target.value }))}
                text="Benchmark para o solver"
              />
            </CCol>
            <CCol md={2}>
              <CFormLabel htmlFor="hardEndDate">Limite Rígido</CFormLabel>
              <CFormInput
                id="hardEndDate"
                type="date"
                value={form.school_hard_end_date}
                onChange={(e) => setForm((p) => ({ ...p, school_hard_end_date: e.target.value }))}
                text="Hard stop: as aulas não passam desta data"
              />
            </CCol>
            <CCol md={4}>
              <CFormLabel htmlFor="regionCode">Região (Feriados Municipais)</CFormLabel>
              <CFormSelect
                id="regionCode"
                value={form.region_code}
                onChange={(e) => setForm((p) => ({ ...p, region_code: e.target.value }))}
              >
                <option value="">— Apenas feriados nacionais —</option>
                {regions.map((r) => (
                  <option key={r} value={r}>{formatRegionLabel(r)}</option>
                ))}
              </CFormSelect>
            </CCol>
            <CCol md={2}>
              <CFormLabel htmlFor="lunchStart">Almoço Início</CFormLabel>
              <CFormInput
                id="lunchStart"
                type="time"
                value={form.lunch_window_start}
                onChange={(e) => setForm((p) => ({ ...p, lunch_window_start: e.target.value }))}
              />
            </CCol>
            <CCol md={2}>
              <CFormLabel htmlFor="lunchEnd">Almoço Fim</CFormLabel>
              <CFormInput
                id="lunchEnd"
                type="time"
                value={form.lunch_window_end}
                onChange={(e) => setForm((p) => ({ ...p, lunch_window_end: e.target.value }))}
              />
            </CCol>
            <CCol md={2}>
              <CFormLabel htmlFor="lunchMin">Almoço Mínimo (min)</CFormLabel>
              <CFormInput
                id="lunchMin"
                type="number"
                min={1}
                value={form.lunch_min_duration_minutes}
                onChange={(e) => setForm((p) => ({ ...p, lunch_min_duration_minutes: e.target.value }))}
              />
            </CCol>
            <CCol md={2} className="d-flex align-items-end">
              <CButton
                color="primary"
                className="w-100"
                onClick={handleSave}
                disabled={!form.academic_year || upsertMutation.isPending}
              >
                <CIcon icon={cilSave} className="me-1" />
                {upsertMutation.isPending ? 'A guardar...' : 'Guardar'}
              </CButton>
            </CCol>
          </CRow>
        </CCardBody>
      </CCard>

      {settingsListContent}
    </div>
  )
}

SettingsSection.propTypes = {
  regions: PropTypes.arrayOf(PropTypes.string).isRequired,
  onYearsChange: PropTypes.func.isRequired,
}

// ==========================================
//  SECÇÃO 3 — Grelha Horária (existente)
// ==========================================

const GridSection = () => {
  const queryClient = useQueryClient()
  const orgId = useAuthStore(state => state.user?.orgId)
  const [successMsg, setSuccessMsg] = useState(null)
  const [formData, setFormData] = useState({
    start_time: '08:00',
    end_time: '18:00',
    slot_duration_minutes: 50,
    break_duration_minutes: 10,
    days: { 0: true, 1: true, 2: true, 3: true, 4: true, 5: false, 6: false },
  })

  const mutation = useMutation({
    mutationFn: (payload) => apiClient.post('/timeslots/generate', payload),
    onSuccess: () => {
      setSuccessMsg('Configuração aplicada! A grelha de horários foi regenerada.')
      void queryClient.invalidateQueries({ queryKey: ['timeslots', orgId] })
      void queryClient.invalidateQueries({ queryKey: ['weekSchedule', orgId] })
      setTimeout(() => setSuccessMsg(null), 3000)
    },
  })

  const handleSubmit = () => {
    const selectedDays = Object.keys(formData.days)
      .filter((d) => formData.days[d])
      .map((d) => Number.parseInt(d, 10))

    mutation.mutate({
      start_time: `${formData.start_time}:00`,
      end_time: `${formData.end_time}:00`,
      slot_duration_minutes: Number.parseInt(formData.slot_duration_minutes, 10),
      break_duration_minutes: Number.parseInt(formData.break_duration_minutes, 10),
      days_of_week: selectedDays,
    })
  }

  const toggleDay = (idx) => {
    setFormData((prev) => ({ ...prev, days: { ...prev.days, [idx]: !prev.days[idx] } }))
  }

  const daysLabel = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']

  return (
    <div>
      {successMsg && <CAlert color="success">{successMsg}</CAlert>}
      {mutation.isError && <CAlert color="danger">Erro ao guardar configuração.</CAlert>}

      <p className="text-muted mb-4">
        Defina aqui o funcionamento geral da escola. Ao guardar, o sistema irá{' '}
        <strong>regenerar todos os blocos horários</strong> base (Timeslots).
      </p>

      <CForm>
        <CRow className="mb-4">
          <CCol md={3}>
            <CFormInput
              id="gridStart"
              type="time"
              label="Abertura da Escola"
              value={formData.start_time}
              onChange={(e) => setFormData({ ...formData, start_time: e.target.value })}
            />
          </CCol>
          <CCol md={3}>
            <CFormInput
              id="gridEnd"
              type="time"
              label="Fecho da Escola"
              value={formData.end_time}
              onChange={(e) => setFormData({ ...formData, end_time: e.target.value })}
            />
          </CCol>
          <CCol md={3}>
            <CFormInput
              id="slotDuration"
              type="number"
              label="Duração da Aula (min)"
              value={formData.slot_duration_minutes}
              onChange={(e) => setFormData({ ...formData, slot_duration_minutes: e.target.value })}
            />
          </CCol>
          <CCol md={3}>
            <CFormInput
              id="breakDuration"
              type="number"
              label="Intervalo (min)"
              value={formData.break_duration_minutes}
              onChange={(e) => setFormData({ ...formData, break_duration_minutes: e.target.value })}
              text="Tempo de pausa entre aulas"
            />
          </CCol>
        </CRow>

        <fieldset className="mb-4">
          <legend className="form-label fw-bold d-block mb-2">Dias de Funcionamento</legend>
          <div className="d-flex gap-2 flex-wrap">
            {daysLabel.map((label, idx) => (
              <CFormCheck
                key={label}
                button={{
                  color: formData.days[idx] ? 'primary' : 'secondary',
                  variant: formData.days[idx] ? '' : 'outline',
                }}
                type="checkbox"
                id={`day-${idx}`}
                label={label}
                checked={formData.days[idx]}
                onChange={() => toggleDay(idx)}
              />
            ))}
          </div>
        </fieldset>

        <div className="d-grid gap-2 d-md-flex justify-content-md-end">
          <CButton
            color="primary"
            size="lg"
            onClick={handleSubmit}
            disabled={mutation.isPending}
          >
            <CIcon icon={cilSave} className="me-2" />
            {mutation.isPending ? 'A Processar...' : 'Guardar e Regenerar Grelha'}
          </CButton>
        </div>
      </CForm>
    </div>
  )
}

// ==========================================
//  COMPONENTE PRINCIPAL
// ==========================================

const SchoolConfig = () => {
  const { user } = useAuthStore()
  const [academicYears, setAcademicYears] = useState([])
  const [activeTab, setActiveTab] = useState('settings')

  const { data: regionsData } = useQuery({
    queryKey: ['available-regions'],
    queryFn: async () => {
      const { data } = await apiClient.get('/school/settings/regions')
      return data.regions
    },
    staleTime: Number.POSITIVE_INFINITY, // Lista de regiões não muda
  })

  const regions = regionsData ?? []

  return (
    <div className="p-4">
      <h2 className="mb-4 fw-bold text-dark">
        <CIcon icon={cilSettings} className="me-2" />
        Configuração da Escola
      </h2>

      {user?.orgName && (
        <CAlert color="primary" className="d-flex align-items-center gap-2 py-2 mb-4">
          A gerir organização:{' '}
          <CBadge color="light" textColor="primary" className="fs-6">
            {user.orgName}
          </CBadge>
        </CAlert>
      )}

      <CTabs activeItemKey={activeTab} onChange={(key) => setActiveTab(key)}>
        <CTabList variant="tabs" className="mb-4">
          <CTab itemKey="settings">Anos Letivos</CTab>
          <CTab itemKey="calendar">Calendário Escolar</CTab>
          <CTab itemKey="grid">Grelha Horária</CTab>
        </CTabList>

        <CTabContent>
          <CTabPanel itemKey="settings">
            <CCard className="border-0 shadow-sm">
              <CCardHeader className="bg-white fw-bold py-3">Configurações por Ano Letivo</CCardHeader>
              <CCardBody className="p-4">
                <SettingsSection regions={regions} onYearsChange={setAcademicYears} />
              </CCardBody>
            </CCard>
          </CTabPanel>

          <CTabPanel itemKey="calendar">
            <CCard className="border-0 shadow-sm">
              <CCardHeader className="bg-white fw-bold py-3">Calendário Escolar (Feriados e Pausas)</CCardHeader>
              <CCardBody className="p-4">
                {academicYears.length === 0 ? (
                  <CAlert color="warning">
                    Configure pelo menos um ano letivo no separador{' '}
                    <strong>Anos Letivos</strong> antes de gerir o calendário.
                  </CAlert>
                ) : (
                  <CalendarSection academicYears={academicYears} />
                )}
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