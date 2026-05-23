import React, { useState, useEffect } from 'react'
import {
  CForm, CCol, CRow, CFormInput, CButton, CModalFooter, CCard, CCardBody, CAlert, CBadge,
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilArrowRight, cilArrowLeft, cilTrash, cilPlus, cilCheckCircle, cilWarning, cilInfo } from '@coreui/icons'
import PropTypes from 'prop-types'

const getStepBadgeColor = (step, s) => {
  if (step === s) return 'primary'
  if (step > s) return 'success'
  return 'light'
}

const fieldErrorClass = (classError, ...keywords) =>
  classError && keywords.some(kw => classError.includes(kw)) ? 'is-invalid' : ''

const CourseForm = ({ initialData, onSubmit, isLoading, onCancel }) => {
  // --- WIZARD STATE (2 passos: Info + Turmas) ---
  const [step, setStep] = useState(1)
  const [formError, setFormError] = useState(null)

  // --- FORM DATA STATE ---
  const [formData, setFormData] = useState({
    name: '',
    abbreviation: '',
    subject_ids: [],     // Vazio — disciplinas são geridas por turma na página ClassSubjects
    classes_config: []   // Array de objetos [{ name, grade_level, start_year, end_year, size }]
  })

  // --- STATE TEMPORÁRIO PARA ADICIONAR TURMAS ---
  // Vamos assumir ano letivo atual como default
  const currentYear = new Date().getFullYear();
  const [newClass, setNewClass] = useState({ 
    name: '', 
    grade_level: 10,
    start_year: currentYear, // Novo campo obrigatório
    end_year: currentYear + 3, // Default: Ciclo de 3 anos
    size: 25 // Default do backend
  })
  const [classError, setClassError] = useState(null)

  // --- POPULAR DADOS NA EDIÇÃO ---
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (initialData) {
      setFormData({
        name: initialData.name || '',
        abbreviation: initialData.abbreviation || '',
        subject_ids: [], // Disciplinas geridas por turma
        classes_config: initialData.classes
          ? initialData.classes.map(cls => ({
              name: cls.name || '',
              grade_level: cls.grade_level || 10,
              start_year: cls.start_year || currentYear,
              end_year: cls.end_year || currentYear + 3,
              size: cls.size || 25
            }))
          : []
      })
      setStep(1)
    }
  }, [initialData, currentYear])
  /* eslint-enable react-hooks/set-state-in-effect */

  // --- HANDLERS PASSO 1 ---
  const handleInputChange = (e) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
    setFormError(null)
  }

  const handleNextStep = () => {
    // VALIDAÇÃO 1: Nome obrigatório
    if (!formData.name?.trim()) {
      setFormError('Nome do curso é obrigatório.')
      return
    }

    // VALIDAÇÃO 2: Sigla obrigatória
    if (!formData.abbreviation?.trim()) {
      setFormError('Sigla do curso é obrigatória (ex: TGEI).')
      return
    }

    // VALIDAÇÃO 3: Sigla com comprimento razoável
    if (formData.abbreviation.trim().length < 2) {
      setFormError('A sigla deve ter pelo menos 2 caracteres.')
      return
    }

    setFormError(null)
    setStep(2)
  }

  // --- HANDLERS PASSO 2: TURMAS ---
  const handleClassInputChange = (field, value) => {
    setNewClass(prev => ({ ...prev, [field]: value }))
    setClassError(null)
  }

  // Lógica de Turmas (Atualizada com validação robusta)
  const addClassConfig = () => {
    // VALIDAÇÃO 1: Nome obrigatório
    if (!newClass.name?.trim()) {
      setClassError('Nome da turma é obrigatório')
      return
    }

    // VALIDAÇÃO 2: Grade level (10-12)
    const gradeLevel = Number.parseInt(newClass.grade_level, 10)
    if (Number.isNaN(gradeLevel) || gradeLevel < 10 || gradeLevel > 12) {
      setClassError('Ano escolar deve ser 10, 11 ou 12')
      return
    }

    // VALIDAÇÃO 3: Start year obrigatório e válido
    const startYear = Number.parseInt(newClass.start_year, 10)
    if (Number.isNaN(startYear) || startYear < 2000 || startYear > 2100) {
      setClassError('Ano de início deve ser entre 2000 e 2100')
      return
    }

    // VALIDAÇÃO 4: End year obrigatório e válido
    const endYear = Number.parseInt(newClass.end_year, 10)
    if (Number.isNaN(endYear) || endYear < 2000 || endYear > 2100) {
      setClassError('Ano de fim deve ser entre 2000 e 2100')
      return
    }

    // VALIDAÇÃO 5: CRÍTICO - Start <= End
    if (startYear > endYear) {
      setClassError(`Erro: Ano de início (${startYear}) não pode ser maior que ano de fim (${endYear})`)
      return
    }

    // VALIDAÇÃO 6: Proteção contra duplicação de nomes no mesmo curso
    const isDuplicate = formData.classes_config.some(cls => cls.name.toLowerCase() === newClass.name.toLowerCase())
    if (isDuplicate) {
      setClassError(`A turma "${newClass.name}" já foi adicionada neste curso`)
      return
    }

    // VALIDAÇÃO 7: Tamanho válido (se editável)
    const size = Number.parseInt(newClass.size, 10)
    if (Number.isNaN(size) || size < 1 || size > 100) {
      setClassError('Tamanho da turma deve ser entre 1 e 100')
      return
    }

    // ✅ TODAS AS VALIDAÇÕES PASSARAM - Adicionar à lista
    setFormData(prev => ({
      ...prev,
      classes_config: [...prev.classes_config, { 
        name: newClass.name.trim(),
        grade_level: gradeLevel,
        start_year: startYear,
        end_year: endYear,
        size: size
      }]
    }))

    // Reset COMPLETO dos campos (não mantém valores antigos)
    setNewClass({
      name: '',
      grade_level: 10,
      start_year: currentYear,
      end_year: currentYear + 3,
      size: 25
    })
    setClassError(null) // Limpar erro após sucesso
  }

  const removeClassConfig = (index) => {
    setFormData(prev => ({
      ...prev,
      classes_config: prev.classes_config.filter((_, i) => i !== index)
    }))
  }

  // --- SUBMIT FINAL ---
  const handleSubmit = (e) => {
    e.preventDefault()
    // Enviar tudo de uma vez (Atomic - Stability)
    onSubmit(formData)
  }

  // --- RENDER ---

  return (
    <CForm onSubmit={handleSubmit}>
      {/* INDICADOR DE PASSOS */}
      <div className="d-flex justify-content-center mb-4">
        {[1, 2].map(s => (
          <CBadge
            key={s}
            color={getStepBadgeColor(step, s)}
            shape="rounded-pill"
            className={`mx-1 px-3 py-2 ${step < s ? 'text-muted border' : ''}`}
          >
            {s === 1 && '1. Informações'}
            {s === 2 && '2. Turmas'}
          </CBadge>
        ))}
      </div>

      {/* PASSO 1: INFORMAÇÃO BÁSICA */}
      {step === 1 && (
        <>
          {formError && (
            <CAlert color="danger" className="mb-3">
              {formError}
            </CAlert>
          )}

          <div className="mb-3 pb-3 border-bottom">
            <h5 className="mb-0">
              <span className="badge bg-primary me-2">1</span>
              {' '}Informações Básicas
            </h5>
            <small className="text-muted">Nome e sigla do curso</small>
          </div>

          <CRow className="g-3">
            <CCol md={8}>
              <CFormInput
                type="text"
                label="Nome do Curso"
                name="name"
                value={formData.name}
                onChange={handleInputChange}
                required
                placeholder="Ex: Técnico em Informática"
                autoFocus
              />
            </CCol>

            <CCol md={4}>
              <CFormInput
                type="text"
                label="Sigla"
                name="abbreviation"
                value={formData.abbreviation}
                onChange={handleInputChange}
                required
                placeholder="Ex: TGEI"
                maxLength={10}
              />
              <div className="form-text">Deve ser única (ex: TGEI-25)</div>
            </CCol>
          </CRow>

          <CModalFooter className="px-0 mt-4 border-0 pb-0">
            <CButton color="secondary" variant="ghost" onClick={onCancel}>
              Cancelar
            </CButton>
            <CButton color="primary" onClick={handleNextStep}>
              Próximo: Turmas <CIcon icon={cilArrowRight} className="ms-2" />
            </CButton>
          </CModalFooter>
        </>
      )}

      {/* PASSO 2: CONFIGURAÇÃO DE TURMAS */}
      {step === 2 && (
        <div className="animate-fade-in">
          <div className="mb-3 pb-3 border-bottom">
            <h5 className="mb-0">
              <span className="badge bg-primary me-2">2</span>
              {' '}Gerar Turmas Iniciais
            </h5>
            <small className="text-muted">Configure as turmas e o ciclo de anos (ex: 2025-2028). Opcional.</small>
          </div>

          {/* ERRO DO PASSO 2 */}
          {classError && (
            <CAlert color="danger" dismissible onClose={() => setClassError(null)} className="mb-3">
              <CIcon icon={cilWarning} size="sm" className="me-1" />
              <strong>Erro:</strong> {classError}
            </CAlert>
          )}

          <CCard className="mb-3 bg-light border-0">
            <CCardBody className="p-3">
              {/* Linha 1: Nome e Ano Escolar */}
              <CRow className="g-2 align-items-end mb-2">
                <CCol xs={8}>
                  <label htmlFor="newClassName" className="form-label small mb-1">Nome Turma <span className="text-danger">*</span></label>
                  <CFormInput
                    id="newClassName"
                    size="sm"
                    placeholder="Ex: 10º TGEI"
                    value={newClass.name}
                    onChange={(e) => handleClassInputChange('name', e.target.value)}
                    className={fieldErrorClass(classError, 'Nome')}
                  />
                </CCol>
                <CCol xs={4}>
                  <label htmlFor="newClassGrade" className="form-label small mb-1">Ano (10-12) <span className="text-danger">*</span></label>
                  <CFormInput
                    id="newClassGrade"
                    size="sm"
                    type="number"
                    min="10" max="12"
                    value={newClass.grade_level}
                    onChange={(e) => handleClassInputChange('grade_level', e.target.value)}
                    className={fieldErrorClass(classError, 'Ano escolar')}
                  />
                </CCol>
              </CRow>

              {/* Linha 2: Anos de Calendário + Tamanho */}
              <CRow className="g-2 align-items-end mb-3">
                <CCol xs={4}>
                  <label htmlFor="newClassStartYear" className="form-label small mb-1">Início (ex: 2025) <span className="text-danger">*</span></label>
                  <CFormInput
                    id="newClassStartYear"
                    size="sm"
                    type="number"
                    placeholder="2025"
                    value={newClass.start_year}
                    onChange={(e) => handleClassInputChange('start_year', e.target.value)}
                    className={fieldErrorClass(classError, 'início', 'Ano de início')}
                  />
                </CCol>
                <CCol xs={4}>
                  <label htmlFor="newClassEndYear" className="form-label small mb-1">Fim (ex: 2028) <span className="text-danger">*</span></label>
                  <CFormInput
                    id="newClassEndYear"
                    size="sm"
                    type="number"
                    placeholder="2028"
                    value={newClass.end_year}
                    onChange={(e) => handleClassInputChange('end_year', e.target.value)}
                    className={fieldErrorClass(classError, 'fim', 'Ano de fim', 'maior')}
                  />
                </CCol>
                <CCol xs={4}>
                  <label htmlFor="newClassSize" className="form-label small mb-1">Alunos</label>
                  <CFormInput
                    id="newClassSize"
                    size="sm"
                    type="number"
                    min="1" max="100"
                    value={newClass.size}
                    onChange={(e) => handleClassInputChange('size', e.target.value)}
                    className={fieldErrorClass(classError, 'Tamanho')}
                  />
                </CCol>
              </CRow>

              {/* Linha 3: Botão de confirmar adição — separado e claro */}
              <CButton
                color="success"
                size="sm"
                className="text-white w-100 d-flex align-items-center justify-content-center gap-1"
                onClick={addClassConfig}
              >
                <CIcon icon={cilPlus} size="sm" /> Adicionar Turma
              </CButton>
            </CCardBody>
          </CCard>

          {/* Lista de Turmas Configuradas */}
          {formData.classes_config.length > 0 ? (
            <div className="mb-3">
              <h6 className="mb-2 text-success">
                <CIcon icon={cilCheckCircle} size="sm" className="me-1" />
                {formData.classes_config.length} turma{formData.classes_config.length === 1 ? '' : 's'} configurada{formData.classes_config.length === 1 ? '' : 's'}
              </h6>
              <ul className="list-group text-sm">
                {formData.classes_config.map((cls, index) => (
                  <li key={cls.name} className="list-group-item d-flex justify-content-between align-items-center py-2">
                    <div>
                      <span className="fw-bold d-block">{cls.name}</span>
                      <span className="text-muted small">
                        {cls.grade_level}º Ano ({cls.start_year}-{cls.end_year}) · {cls.size} alunos
                      </span>
                    </div>
                    <CButton color="danger" variant="ghost" size="sm" onClick={() => removeClassConfig(index)}>
                      <CIcon icon={cilTrash} />
                    </CButton>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <CAlert color="info" className="text-center py-2 text-muted small">
              <CIcon icon={cilInfo} size="sm" className="me-1" />
              Sem turmas. O curso será criado apenas como estrutura curricular (pode adicionar turmas depois).
            </CAlert>
          )}

          <div className="mt-2 mb-3">
            <CAlert color="info" className="py-2 small mb-0">
              <CIcon icon={cilInfo} size="sm" className="me-1" />
              As disciplinas são adicionadas depois, na página de gestão de cada turma.
            </CAlert>
          </div>

          <CModalFooter className="px-0 mt-4 border-0 pb-0">
            <CButton color="secondary" variant="outline" onClick={() => setStep(1)}>
              <CIcon icon={cilArrowLeft} className="me-2" /> Anterior
            </CButton>
            <CButton color="secondary" variant="ghost" onClick={onCancel}>
              Cancelar
            </CButton>
            <CButton color="success" type="submit" disabled={isLoading} className="text-white">
              {isLoading ? (
                <>
                  <span className="spinner-border spinner-border-sm me-2"></span>
                  {' '}A processar...
                </>
              ) : (
                <span className="d-flex align-items-center">
                  <CIcon icon={cilCheckCircle} className="me-2" />
                  {initialData ? 'Atualizar Curso' : 'Criar Curso Completo'}
                </span>
              )}
            </CButton>
          </CModalFooter>
        </div>
      )}
    </CForm>
  )
}

CourseForm.propTypes = {
  initialData: PropTypes.shape({
    name: PropTypes.string,
    abbreviation: PropTypes.string,
    classes: PropTypes.array,
  }),
  onSubmit: PropTypes.func.isRequired,
  isLoading: PropTypes.bool,
  onCancel: PropTypes.func.isRequired,
}

export default CourseForm

