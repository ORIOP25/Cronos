import { useState } from 'react'
import {
  CAlert,
  CButton,
  CCol,
  CForm,
  CFormInput,
  CFormSelect,
  CModalFooter,
  CRow,
} from '@coreui/react'
import { EMPTY_MODULE, normalizeModule } from '../../utils/subjectModules'
import { ROOM_TYPES } from '../../utils/presentation'

function createInitialSubject(initialData) {
  return {
    name: initialData?.name ?? '',
    required_room_type: initialData?.required_room_type ?? 'normal',
    modules: (initialData?.modules ?? []).map((module) => normalizeModule(module)).filter(Boolean),
  }
}

const SubjectForm = ({ initialData, onSubmit, isLoading, onCancel, readOnly = false }) => {
  const [subject, setSubject] = useState(() => createInitialSubject(initialData))
  const [moduleDraft, setModuleDraft] = useState(EMPTY_MODULE)
  const [editingIndex, setEditingIndex] = useState(null)
  const [error, setError] = useState('')

  const updateSubject = (field, value) => {
    if (readOnly) return
    setSubject((current) => ({ ...current, [field]: value }))
    setError('')
  }

  const updateModule = (field, value) => {
    if (readOnly) return
    setModuleDraft((current) => ({ ...current, [field]: value }))
    setError('')
  }

  const saveModule = () => {
    if (readOnly) return
    const normalized = normalizeModule(moduleDraft)
    if (!normalized) return setError('Indique o nome e um número de horas válido para o módulo.')
    setSubject((current) => ({
      ...current,
      modules: editingIndex == null
        ? [...current.modules, normalized]
        : current.modules.map((module, index) => index === editingIndex
          ? { ...normalized, ...(module.id == null ? {} : { id: module.id }) }
          : module),
    }))
    setModuleDraft(EMPTY_MODULE)
    setEditingIndex(null)
  }

  const startEditing = (index) => {
    if (readOnly) return
    const module = subject.modules[index]
    setModuleDraft({ name: module.name, code: module.code, hours_total: module.hours_total })
    setEditingIndex(index)
  }

  const cancelEditing = () => {
    setModuleDraft(EMPTY_MODULE)
    setEditingIndex(null)
  }

  const submit = (event) => {
    event.preventDefault()
    if (readOnly) return
    const name = subject.name.trim()
    if (!name) return setError('Nome da disciplina é obrigatório.')
    onSubmit({
      name,
      required_room_type: subject.required_room_type,
      modules: subject.modules.map((module, order) => ({ ...module, order })),
    })
  }

  return (
    <CForm onSubmit={submit}>
      {error && <CAlert color="danger">{error}</CAlert>}

      <fieldset className="mb-4">
        <legend className="h6 mb-3">Dados gerais</legend>
        <CRow className="g-3">
          <CCol md={8}>
            <CFormInput id="subject-name" label="Nome da Disciplina" value={subject.name} onChange={(event) => updateSubject('name', event.target.value)} disabled={readOnly} required />
          </CCol>
          <CCol md={4}>
            <CFormSelect id="subject-room-type" label="Sala Preferencial" value={subject.required_room_type} onChange={(event) => updateSubject('required_room_type', event.target.value)} disabled={readOnly}>
              {Object.entries(ROOM_TYPES).map(([value, metadata]) => <option key={value} value={value}>{metadata.label}</option>)}
            </CFormSelect>
          </CCol>
        </CRow>
      </fieldset>

      <fieldset>
        <legend className="h6 mb-3">Módulos</legend>
        {!readOnly && <CRow className="g-2 align-items-end">
          <CCol md={4}><CFormInput id="subject-module-name" label="Nome do módulo" value={moduleDraft.name} onChange={(event) => updateModule('name', event.target.value)} /></CCol>
          <CCol md={3}><CFormInput id="subject-module-code" label="Código UFCD" value={moduleDraft.code} onChange={(event) => updateModule('code', event.target.value)} /></CCol>
          <CCol md={2}><CFormInput id="subject-module-hours" label="Horas" type="number" min={1} value={moduleDraft.hours_total} onChange={(event) => updateModule('hours_total', event.target.value)} /></CCol>
          <CCol md={3} className="d-grid"><CButton type="button" color="secondary" variant="outline" onClick={saveModule}>{editingIndex == null ? 'Adicionar' : 'Guardar'}</CButton></CCol>
        </CRow>}
        {editingIndex != null && <CButton type="button" color="secondary" variant="ghost" size="sm" onClick={cancelEditing}>Cancelar edição</CButton>}

        <div className="mt-3 d-grid gap-2">
          {subject.modules.map((module, index) => (
            <div key={module.id ?? `${module.name}-${index}`} className="module-item-card d-flex justify-content-between align-items-center">
              <span className="me-2 text-break" style={{ minWidth: 0 }}><strong>{module.name}</strong> · <small className="text-muted">{module.code || 'Sem código'}</small> · <strong>{module.hours_total}h</strong></span>
              {!readOnly && <div className="d-flex align-items-center flex-shrink-0 text-nowrap">
                <CButton type="button" color="primary" variant="ghost" size="sm" aria-label={`Editar ${module.name}`} onClick={() => startEditing(index)}>Editar</CButton>
                <CButton type="button" color="danger" variant="ghost" size="sm" aria-label={`Remover ${module.name}`} onClick={() => setSubject((current) => ({ ...current, modules: current.modules.filter((_, moduleIndex) => moduleIndex !== index) }))}>Remover</CButton>
              </div>}
            </div>
          ))}
        </div>
      </fieldset>

      <CModalFooter className="px-0 mt-4 border-0 pb-0">
        <CButton type="button" color="secondary" variant="ghost" onClick={onCancel}>Cancelar</CButton>
        {!readOnly && <CButton type="submit" color="primary" disabled={isLoading}>{isLoading ? 'A guardar...' : 'Guardar Disciplina'}</CButton>}
      </CModalFooter>
    </CForm>
  )
}

export default SubjectForm
