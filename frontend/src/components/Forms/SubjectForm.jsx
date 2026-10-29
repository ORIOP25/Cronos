import { useRef, useState } from 'react'
import {
  CButton,
  CCol,
  CForm,
  CFormFeedback,
  CFormInput,
  CFormSelect,
  CModalFooter,
  CRow,
} from '@coreui/react'
import { EMPTY_MODULE, normalizeModule } from '../../utils/subjectModules'
import { useRoomTypes } from '../../features/catalog/data'
import { TXT } from '../../utils/terminology'

const SUBJECT_FEEDBACK_ID = 'subjectNameFeedback'
const MODULES_FEEDBACK_ID = 'subjectModulesFeedback'

function createInitialSubject(initialData) {
  return {
    name: initialData?.name ?? '',
    room_type_id: initialData?.room_type?.id ?? initialData?.room_type_id ?? '',
    modules: (initialData?.modules ?? []).map((module) => normalizeModule(module)).filter(Boolean),
  }
}

const SubjectForm = ({ initialData, onSubmit, isLoading, onCancel, readOnly = false }) => {
  const { data: roomTypes = [], isLoading: roomTypesLoading, isError: roomTypesError, refetch } = useRoomTypes()
  const normalRoomType = roomTypes.find((roomType) => roomType.is_normal)
  const roomTypesUnavailable = !roomTypesLoading && (roomTypesError || !normalRoomType)
  const roomTypesErrorMessage = roomTypesError
    ? 'Não foi possível carregar os tipos de sala.'
    : !roomTypesLoading && !normalRoomType
      ? 'Não existem tipos de sala disponíveis.'
      : ''
  const [subject, setSubject] = useState(() => createInitialSubject(initialData))
  const [moduleDraft, setModuleDraft] = useState(EMPTY_MODULE)
  const [editingIndex, setEditingIndex] = useState(null)
  const [validation, setValidation] = useState(null)
  const subjectNameRef = useRef(null)
  const firstModuleRef = useRef(null)

  const updateSubject = (field, value) => {
    if (readOnly) return
    const next = { ...subject, [field]: value }
    setSubject(next)
    if (validation?.field === 'subject-name' && next.name.trim()) setValidation(null)
  }

  const updateModule = (field, value) => {
    if (readOnly) return
    const next = { ...moduleDraft, [field]: value }
    setModuleDraft(next)
    if (validation?.field === 'modules' && normalizeModule(next)) setValidation(null)
  }

  const saveModule = () => {
    if (readOnly) return
    const normalized = normalizeModule(moduleDraft)
    if (!normalized) {
      setValidation({ message: 'Indique o nome e um número de horas válido para o módulo.', field: 'modules' })
      firstModuleRef.current?.focus()
      return
    }
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
    setValidation(null)
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
    if (readOnly || roomTypesLoading || roomTypesError || !normalRoomType) return
    const name = subject.name.trim()
    if (!name) {
      setValidation({ message: 'Nome da disciplina é obrigatório.', field: 'subject-name' })
      subjectNameRef.current?.focus()
      return
    }
    onSubmit({
      name,
      room_type_id: Number(subject.room_type_id || normalRoomType.id),
      modules: subject.modules.map((module, order) => ({ ...module, order })),
    })
  }

  const modulesInvalid = validation?.field === 'modules'
  const moduleInputProps = {
    invalid: modulesInvalid || undefined,
    'aria-invalid': modulesInvalid || undefined,
    'aria-describedby': modulesInvalid ? MODULES_FEEDBACK_ID : undefined,
  }

  const submitLabel = initialData ? TXT.SAVE_CHANGES : 'Criar disciplina'

  return (
    <CForm onSubmit={submit} noValidate>
      <fieldset className="mb-4">
        <legend className="h6 mb-3">Dados gerais</legend>
        <CRow className="g-3">
          <CCol md={8}>
            <CFormInput
              id="subject-name"
              label="Nome da disciplina"
              value={subject.name}
              onChange={(event) => updateSubject('name', event.target.value)}
              disabled={readOnly}
              required
              invalid={validation?.field === 'subject-name' || undefined}
              aria-invalid={validation?.field === 'subject-name' || undefined}
              aria-describedby={validation?.field === 'subject-name' ? SUBJECT_FEEDBACK_ID : undefined}
              ref={subjectNameRef}
            />
            {validation?.field === 'subject-name' && (
              <CFormFeedback id={SUBJECT_FEEDBACK_ID} invalid className="d-block" role="alert">{validation.message}</CFormFeedback>
            )}
          </CCol>
          <CCol md={4}>
            <CFormSelect
              id="subject-room-type"
              label="Tipo de sala"
              value={String(subject.room_type_id || normalRoomType?.id || '')}
              onChange={(event) => updateSubject('room_type_id', event.target.value)}
              disabled={readOnly || roomTypesLoading || roomTypesUnavailable}
              required
              aria-invalid={roomTypesErrorMessage ? 'true' : undefined}
              aria-describedby={roomTypesLoading ? 'room-types-loading' : roomTypesErrorMessage ? 'room-types-error' : undefined}
            >
              {roomTypes.map((roomType) => <option key={roomType.id} value={roomType.id}>{roomType.name}</option>)}
            </CFormSelect>
            {roomTypesLoading && <div id="room-types-loading" role="status" aria-live="polite" className="form-text">A carregar tipos de sala…</div>}
            {roomTypesErrorMessage && (
              <div id="room-types-error">
                <CFormFeedback invalid className="d-block" role="alert">{roomTypesErrorMessage}</CFormFeedback>
                {roomTypesError && <CButton type="button" color="secondary" variant="outline" size="sm" onClick={() => refetch()}>Tentar novamente</CButton>}
              </div>
            )}
          </CCol>
        </CRow>
      </fieldset>

      <fieldset>
        <legend className="h6 mb-3">Módulos</legend>
        {!readOnly && <CRow className="g-2 align-items-end">
          <CCol md={4}><CFormInput id="subject-module-name" label="Nome do módulo" value={moduleDraft.name} onChange={(event) => updateModule('name', event.target.value)} ref={firstModuleRef} {...moduleInputProps} /></CCol>
          <CCol md={3}><CFormInput id="subject-module-code" label="Código UFCD" value={moduleDraft.code} onChange={(event) => updateModule('code', event.target.value)} {...moduleInputProps} /></CCol>
          <CCol md={2}><CFormInput id="subject-module-hours" label="Horas" type="number" min={1} value={moduleDraft.hours_total} onChange={(event) => updateModule('hours_total', event.target.value)} {...moduleInputProps} /></CCol>
          <CCol md={3} className="d-grid"><CButton type="button" color="secondary" variant="outline" onClick={saveModule}>{editingIndex == null ? 'Adicionar' : 'Guardar'}</CButton></CCol>
        </CRow>}
        {modulesInvalid && (
          <CFormFeedback id={MODULES_FEEDBACK_ID} invalid className="d-block" role="alert">{validation.message}</CFormFeedback>
        )}
        {editingIndex != null && <CButton type="button" color="secondary" variant="outline" size="sm" onClick={cancelEditing}>Cancelar edição</CButton>}

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
        <CButton type="button" color="secondary" variant="outline" onClick={onCancel}>{readOnly ? TXT.CLOSE : TXT.CANCEL}</CButton>
        {!readOnly && <CButton type="submit" color="primary" disabled={isLoading || roomTypesLoading || roomTypesUnavailable}>{isLoading ? TXT.SAVING : submitLabel}</CButton>}
      </CModalFooter>
    </CForm>
  )
}

export default SubjectForm
