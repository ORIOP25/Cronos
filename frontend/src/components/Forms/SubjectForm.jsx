import React, { useState, useEffect } from 'react'
import {
  CForm, CCol, CRow, CFormInput, CButton, CModalFooter, CFormSelect, CCard, CCardBody, CAlert, CBadge
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilX, cilPencil, cilCheckCircle } from '@coreui/icons'
import PropTypes from 'prop-types'

const SubjectForm = ({ initialData, onSubmit, isLoading, onCancel }) => {
  // --- WIZARD STATE ---
  const [step, setStep] = useState(1) // Passo 1 ou 2
  
  // --- FORM DATA STATE ---
  const [formData, setFormData] = useState({
    name: '',
    required_room_type: 'normal',
    modules: []
  })

  // --- MODULO EM EDIÇÃO (Passo 2) ---
  const [currentModule, setCurrentModule] = useState({
    name: '',
    code: '',
    hours_total: ''
  })

  // --- EDIÇÃO INLINE DE MÓDULOS ---
  const [editingModuleIndex, setEditingModuleIndex] = useState(null)
  const [editModuleData, setEditModuleData] = useState({
    name: '',
    code: '',
    hours_total: ''
  })

  // ✅ Popular dados na Edição (Passo 1 e 2)
  useEffect(() => {
    if (initialData) {
      setFormData({
        name: initialData.name || '',
        required_room_type: initialData.required_room_type || 'normal',
        // Preservar id dos módulos existentes para o backend fazer smart diff
        modules: (initialData.modules || []).map(m => ({
          id: m.id || undefined,
          name: m.name,
          code: m.code || '',
          hours_total: m.hours_total,
          order: m.order
        }))
      })
    }
  }, [initialData])

  // --- HANDLERS ---

  const handleInputChange = (e) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
  }

  const handleModuleChange = (e) => {
    const { name, value } = e.target
    setCurrentModule(prev => ({ ...prev, [name]: value }))
  }

  const handleAddModule = () => {
    // Validação simples
    if (!currentModule.name || !currentModule.hours_total) return

    setFormData(prev => ({
      ...prev,
      modules: [
        ...prev.modules,
        {
          ...currentModule,
          order: prev.modules.length, // Auto-ordenação
          hours_total: Number.parseInt(currentModule.hours_total, 10)
          // Sem id = módulo novo
        }
      ]
    }))

    // Reset inputs do módulo
    setCurrentModule({ name: '', code: '', hours_total: '' })
  }

  const handleRemoveModule = (indexToRemove) => {
    setFormData(prev => {
      const filtered = prev.modules.filter((_, i) => i !== indexToRemove)
      // Re-indexar orders para manter sequencial [0, 1, 2...], preservando id
      const reordered = filtered.map((m, i) => ({ ...m, order: i }))
      return { ...prev, modules: reordered }
    })
    // Se estávamos a editar este módulo, fechar edição
    if (editingModuleIndex === indexToRemove) {
      setEditingModuleIndex(null)
    } else if (editingModuleIndex !== null && editingModuleIndex > indexToRemove) {
      setEditingModuleIndex(editingModuleIndex - 1)
    }
  }

  const handleStartEditModule = (index) => {
    const mod = formData.modules[index]
    setEditModuleData({
      name: mod.name,
      code: mod.code || '',
      hours_total: mod.hours_total
    })
    setEditingModuleIndex(index)
  }

  const handleSaveEditModule = () => {
    if (!editModuleData.name || !editModuleData.hours_total) return
    setFormData(prev => ({
      ...prev,
      modules: prev.modules.map((m, i) => 
        i === editingModuleIndex 
          ? { ...m, name: editModuleData.name, code: editModuleData.code, hours_total: Number.parseInt(editModuleData.hours_total, 10) }
          : m
      )
    }))
    setEditingModuleIndex(null)
  }

  const handleCancelEditModule = () => {
    setEditingModuleIndex(null)
  }

  const handleNextStep = () => {
    if (formData.name) setStep(2)
  }

  const handlePreviousStep = () => setStep(1)

  const handleFormSubmit = (e) => {
    e.preventDefault()
    onSubmit(formData)
  }

  return (
    <CForm onSubmit={handleFormSubmit}>
      {/* INDICADOR DE PASSOS */}
      <div className="d-flex justify-content-center mb-4">
        <CBadge color={step === 1 ? 'primary' : 'success'} shape="rounded-pill" className="me-2 px-3 py-2">
          1. Dados Gerais
        </CBadge>
        <span className="text-muted align-self-center mx-2">→</span>
        <CBadge color={step === 2 ? 'primary' : 'secondary'} shape="rounded-pill" className="ms-2 px-3 py-2">
          2. Módulos
        </CBadge>
      </div>

      {/* PASSO 1: DADOS GERAIS */}
      {step === 1 && (
        <div className="animate-fade-in">
          <div className="mb-3">
            <label htmlFor="subjectName" className="form-label">Nome da Disciplina <span className="text-danger">*</span></label>
            <CFormInput
              id="subjectName"
              name="name"
              placeholder="Ex: Matemática A"
              value={formData.name}
              onChange={handleInputChange}
              required
            />
          </div>

          <div className="mb-3">
            <label htmlFor="subjectRoomType" className="form-label">Sala Preferencial</label>
            <CFormSelect
              id="subjectRoomType"
              name="required_room_type"
              value={formData.required_room_type}
              onChange={handleInputChange}
              options={[
                { label: 'Sala Normal', value: 'normal' },
                { label: 'Laboratório Informática', value: 'lab' },
                { label: 'Ginásio', value: 'gym' },
                { label: 'Sala de Artes', value: 'art' }
              ]}
            />
          </div>

          <CModalFooter className="px-0 mt-4 border-0 pb-0">
            <CButton color="secondary" variant="ghost" onClick={onCancel}>
              Cancelar
            </CButton>
            <CButton color="primary" onClick={handleNextStep} disabled={!formData.name}>
              Próximo: Módulos →
            </CButton>
          </CModalFooter>
        </div>
      )}

      {/* PASSO 2: MÓDULOS */}
      {step === 2 && (
        <div className="animate-fade-in">
          <h6 className="mb-3 text-muted">Adicionar Módulos (Opcional)</h6>
          
          {/* ✅ CORREÇÃO 2: Layout do Formulário de Módulos (Melhor Grid) */}
          <CCard className="mb-3 bg-light border-0">
            <CCardBody className="p-3">
              <CRow className="g-2 align-items-end">
                {/* Nome: Mais espaço */}
                <CCol xs={12} sm={5}>
                  <label htmlFor="moduleName" className="form-label small mb-1">Nome Módulo</label>
                  <CFormInput
                    id="moduleName"
                    size="sm"
                    name="name"
                    placeholder="Ex: Geometria"
                    value={currentModule.name}
                    onChange={handleModuleChange}
                  />
                </CCol>
                
                {/* Código: Espaço ajustado para não quebrar o título */}
                <CCol xs={6} sm={3}>
                  <label htmlFor="moduleCode" className="form-label small mb-1 text-nowrap">Cód. UFCD</label>
                  <CFormInput
                    id="moduleCode"
                    size="sm"
                    name="code"
                    placeholder="001"
                    value={currentModule.code}
                    onChange={handleModuleChange}
                  />
                </CCol>
                
                {/* Horas */}
                <CCol xs={3} sm={2}>
                  <label htmlFor="moduleHours" className="form-label small mb-1">Horas</label>
                  <CFormInput
                    id="moduleHours"
                    size="sm"
                    type="number"
                    name="hours_total"
                    placeholder="H"
                    value={currentModule.hours_total}
                    onChange={handleModuleChange}
                  />
                </CCol>
                
                {/* Botão: Texto "Adicionar" completo e alinhado */}
                <CCol xs={3} sm={2} className="d-grid">
                  <CButton 
                    color="success" 
                    size="sm" 
                    className="text-white text-nowrap"
                    onClick={handleAddModule}
                    disabled={!currentModule.name || !currentModule.hours_total}
                    title="Adicionar à lista"
                  >
                    Add
                  </CButton>
                </CCol>
              </CRow>
            </CCardBody>
          </CCard>

          {/* LISTA DE MÓDULOS */}
          {formData.modules.length > 0 ? (
            <CCard className="border overflow-hidden">
              <CCardBody className="p-0 table-responsive" style={{maxHeight: '250px'}}>
                <table className="table table-hover table-striped mb-0 text-sm">
                  <thead className="table-light">
                    <tr>
                      <th className="w-auto px-3">#</th>
                      <th className="w-50">Nome</th>
                      <th className="w-25">Cód.</th>
                      <th className="w-auto">Horas</th>
                      <th className="w-auto"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {formData.modules.map((mod, index) => (
                      <tr key={mod.id ?? `${mod.name}-${mod.order}`} className="align-middle">
                        <td className="px-3 text-muted small">{index + 1}</td>
                        {editingModuleIndex === index ? (
                          <>
                            <td>
                              <CFormInput
                                size="sm"
                                value={editModuleData.name}
                                onChange={(e) => setEditModuleData(prev => ({ ...prev, name: e.target.value }))}
                              />
                            </td>
                            <td>
                              <CFormInput
                                size="sm"
                                value={editModuleData.code}
                                onChange={(e) => setEditModuleData(prev => ({ ...prev, code: e.target.value }))}
                              />
                            </td>
                            <td>
                              <CFormInput
                                size="sm"
                                type="number"
                                value={editModuleData.hours_total}
                                onChange={(e) => setEditModuleData(prev => ({ ...prev, hours_total: e.target.value }))}
                                style={{ width: '70px' }}
                              />
                            </td>
                            <td className="text-end pe-3">
                              <CButton 
                                color="success" 
                                variant="ghost" 
                                size="sm" 
                                onClick={handleSaveEditModule}
                                className="p-1 me-1"
                                title="Confirmar"
                              >
                                <CIcon icon={cilCheckCircle} />
                              </CButton>
                              <CButton 
                                color="secondary" 
                                variant="ghost" 
                                size="sm" 
                                onClick={handleCancelEditModule}
                                className="p-1"
                                title="Cancelar"
                              >
                                <CIcon icon={cilX} />
                              </CButton>
                            </td>
                          </>
                        ) : (
                          <>
                            <td className="fw-semibold">{mod.name}</td>
                            <td className="text-muted small">{mod.code || '-'}</td>
                            <td><CBadge color="info" shape="rounded-pill">{mod.hours_total}h</CBadge></td>
                            <td className="text-end pe-3">
                              <CButton 
                                color="primary" 
                                variant="ghost" 
                                size="sm" 
                                onClick={() => handleStartEditModule(index)}
                                className="p-1 me-1"
                                title="Editar módulo"
                              >
                                <CIcon icon={cilPencil} />
                              </CButton>
                              <CButton 
                                color="danger" 
                                variant="ghost" 
                                size="sm" 
                                onClick={() => handleRemoveModule(index)}
                                className="p-1"
                                title="Remover módulo"
                              >
                                <CIcon icon={cilX} />
                              </CButton>
                            </td>
                          </>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CCardBody>
            </CCard>
          ) : (
            <CAlert color="info" className="d-flex align-items-center sm py-2">
              <CIcon icon={cilX} className="me-2" />
              <div>Sem módulos. Podes criar a disciplina vazia.</div>
            </CAlert>
          )}

          <CModalFooter className="px-0 mt-4 border-0 pb-0">
            <CButton color="secondary" onClick={handlePreviousStep}>
              ← Voltar
            </CButton>
            <div className="ms-auto">
              <CButton color="secondary" variant="ghost" onClick={onCancel} className="me-2">
                Cancelar
              </CButton>
              <CButton color="success" type="submit" className="text-white" disabled={isLoading}>
                {isLoading ? 'A gravar...' : `Gravar (${formData.modules.length} mód.)`}
              </CButton>
            </div>
          </CModalFooter>
        </div>
      )}
    </CForm>
  )
}

SubjectForm.propTypes = {
  initialData: PropTypes.shape({
    name: PropTypes.string,
    required_room_type: PropTypes.string,
    modules: PropTypes.array,
  }),
  onSubmit: PropTypes.func.isRequired,
  isLoading: PropTypes.bool,
  onCancel: PropTypes.func.isRequired,
}

export default SubjectForm