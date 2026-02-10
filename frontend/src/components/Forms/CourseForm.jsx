import React, { useState, useEffect } from 'react'
import {
  CForm, CCol, CRow, CFormInput, CButton, CModalFooter, CCard, CCardBody, CAlert, CBadge, CFormCheck
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilArrowRight, cilArrowLeft, cilTrash, cilPlus, cilCheckCircle } from '@coreui/icons'
import { useSubjects } from '../../hooks/useSchoolData'

const CourseForm = ({ initialData, onSubmit, isLoading, onCancel }) => {
  // --- WIZARD STATE ---
  const [step, setStep] = useState(1) // Passo 1, 2 ou 3

  // Lista de todas as disciplinas para seleção
  const { data: allSubjects, isLoading: loadingSubjects } = useSubjects()

  // --- FORM DATA STATE (Optimization: Manter local até submit) ---
  const [formData, setFormData] = useState({
    name: '',
    abbreviation: '',
    subject_ids: [],     // Array de IDs [1, 2, 5]
    classes_config: []   // Array de objetos [{ name: "10ºA", grade_level: 10 }]
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

  // --- POPULAR DADOS NA EDIÇÃO (Mesma lógica que SubjectForm) ---
  useEffect(() => {
    if (initialData) {
      // ✅ CORREÇÃO: Restaurar TUDO (name, abbreviation, disciplinas, turmas)
      setFormData({
        name: initialData.name || '',
        abbreviation: initialData.abbreviation || '',
        // Disciplinas: Se vem 'subjects' (objetos), extrai IDs
        subject_ids: initialData.subjects 
          ? initialData.subjects.map(s => s.id) 
          : initialData.subject_ids || [],
        // Turmas: Se vem 'classes' (objetos), transforma em classes_config
        // classes_config precisa de: { name, grade_level, start_year, end_year, size }
        classes_config: initialData.classes 
          ? initialData.classes.map(cls => ({
              name: cls.name || '',
              grade_level: cls.grade_level || 10,
              start_year: cls.start_year || new Date().getFullYear(),
              end_year: cls.end_year || new Date().getFullYear() + 3,
              size: cls.size || 25
            }))
          : []
      })
      setStep(1) // Começa sempre no Passo 1
    }
  }, [initialData])

  // --- HANDLERS PASSO 1 ---
  const handleInputChange = (e) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
  }

  const handleNextStep = () => {
    // VALIDAÇÃO 1: Nome obrigatório
    if (!formData.name || !formData.name.trim()) {
      alert('Nome do curso é obrigatório')
      return
    }

    // VALIDAÇÃO 2: Sigla obrigatória
    if (!formData.abbreviation || !formData.abbreviation.trim()) {
      alert('Sigla do curso é obrigatória (ex: TGEI)')
      return
    }

    // VALIDAÇÃO 3: Sigla com comprimento razoável
    if (formData.abbreviation.trim().length < 2) {
      alert('Sigla deve ter pelo menos 2 caracteres')
      return
    }

    setStep(2)
  }

  // --- HANDLERS PASSO 2: DISCIPLINAS ---
  // Lógica de Seleção de Disciplinas (Toggle ID)
  const toggleSubject = (subjectId) => {
    setFormData(prev => {
      const exists = prev.subject_ids.includes(subjectId)
      if (exists) {
        return { ...prev, subject_ids: prev.subject_ids.filter(id => id !== subjectId) }
      } else {
        return { ...prev, subject_ids: [...prev.subject_ids, subjectId] }
      }
    })
  }

  // --- HANDLERS PASSO 3: TURMAS ---
  const handleClassInputChange = (field, value) => {
    setNewClass(prev => ({ ...prev, [field]: value }))
    setClassError(null)
  }

  // Lógica de Turmas (Atualizada com validação robusta)
  const addClassConfig = () => {
    // VALIDAÇÃO 1: Nome obrigatório
    if (!newClass.name || !newClass.name.trim()) {
      setClassError('Nome da turma é obrigatório')
      return
    }

    // VALIDAÇÃO 2: Grade level (10-12)
    const gradeLevel = parseInt(newClass.grade_level, 10)
    if (isNaN(gradeLevel) || gradeLevel < 10 || gradeLevel > 12) {
      setClassError('Ano escolar deve ser 10, 11 ou 12')
      return
    }

    // VALIDAÇÃO 3: Start year obrigatório e válido
    const startYear = parseInt(newClass.start_year, 10)
    if (isNaN(startYear) || startYear < 2000 || startYear > 2100) {
      setClassError('Ano de início deve ser entre 2000 e 2100')
      return
    }

    // VALIDAÇÃO 4: End year obrigatório e válido
    const endYear = parseInt(newClass.end_year, 10)
    if (isNaN(endYear) || endYear < 2000 || endYear > 2100) {
      setClassError('Ano de fim deve ser entre 2000 e 2100')
      return
    }

    // VALIDAÇÃO 5: CRÍTICO - Start <= End
    if (startYear > endYear) {
      setClassError(`❌ Erro: Ano de início (${startYear}) não pode ser maior que ano de fim (${endYear})`)
      return
    }

    // VALIDAÇÃO 6: Proteção contra duplicação de nomes no mesmo curso
    const isDuplicate = formData.classes_config.some(cls => cls.name.toLowerCase() === newClass.name.toLowerCase())
    if (isDuplicate) {
      setClassError(`A turma "${newClass.name}" já foi adicionada neste curso`)
      return
    }

    // VALIDAÇÃO 7: Tamanho válido (se editável)
    const size = parseInt(newClass.size, 10)
    if (isNaN(size) || size < 1 || size > 100) {
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

  const handlePreviousStep = () => {
    setStep(step - 1)
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
        {[1, 2, 3].map(s => (
          <CBadge
            key={s}
            color={step === s ? 'primary' : step > s ? 'success' : 'light'}
            shape="rounded-pill"
            className={`mx-1 px-3 py-2 ${step < s ? 'text-muted border' : ''}`}
          >
            {s === 1 && '1. Info'}
            {s === 2 && '2. Disciplinas'}
            {s === 3 && '3. Turmas'}
          </CBadge>
        ))}
      </div>

      {/* PASSO 1: INFORMAÇÃO BÁSICA */}
      {step === 1 && (
        <>
          <div className="mb-3 pb-3 border-bottom">
            <h5 className="mb-0">
              <span className="badge bg-primary me-2">1</span>
              Informações Básicas
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
              Próximo: Disciplinas <CIcon icon={cilArrowRight} className="ms-2" />
            </CButton>
          </CModalFooter>
        </>
      )}

      {/* PASSO 2: SELEÇÃO DE DISCIPLINAS */}
      {step === 2 && (
        <>
          <div className="mb-3 pb-3 border-bottom">
            <h5 className="mb-0">
              <span className="badge bg-primary me-2">2</span>
              Plano Curricular
            </h5>
            <small className="text-muted">Selecione as disciplinas que compõem este curso</small>
          </div>

          {loadingSubjects ? (
            <div className="text-center p-5">
              <p className="text-muted">A carregar biblioteca de disciplinas...</p>
            </div>
          ) : (
            <div className="border rounded p-3 bg-light" style={{ maxHeight: '350px', overflowY: 'auto' }}>
              {allSubjects && allSubjects.length > 0 ? (
                <CRow className="g-2">
                  {allSubjects.map(subj => (
                    <CCol xs={12} sm={6} key={subj.id}>
                      <CCard
                        className={`border-0 shadow-sm h-100 cursor-pointer transition-all ${
                          formData.subject_ids.includes(subj.id)
                            ? 'bg-info bg-opacity-10'
                            : 'bg-white'
                        }`}
                        onClick={() => toggleSubject(subj.id)}
                        style={{ cursor: 'pointer', border: formData.subject_ids.includes(subj.id) ? '2px solid #0dcaf0' : '1px solid #dee2e6' }}
                      >
                        <CCardBody className="p-2 d-flex align-items-center">
                          <CFormCheck
                            checked={formData.subject_ids.includes(subj.id)}
                            readOnly
                            className="me-2 mt-0"
                          />
                          <div className="flex-grow-1">
                            <div className="fw-semibold text-sm">{subj.name}</div>
                            <div className="text-muted text-xs">{subj.required_room_type || 'Normal'}</div>
                          </div>
                        </CCardBody>
                      </CCard>
                    </CCol>
                  ))}
                </CRow>
              ) : (
                <CAlert color="warning" className="mb-0">
                  Nenhuma disciplina disponível. Crie disciplinas primeiro.
                </CAlert>
              )}
            </div>
          )}

          <div className="mt-3">
            {formData.subject_ids.length === 0 && (
              <CAlert color="warning" className="mb-2 small">
                ⚠️ <strong>Aviso:</strong> Nenhuma disciplina selecionada. O curso será criado sem plano curricular.
              </CAlert>
            )}
            <div className="text-end">
              <CBadge color={formData.subject_ids.length > 0 ? 'success' : 'light'} shape="rounded-pill" className="text-capitalize">
                ✓ {formData.subject_ids.length} {formData.subject_ids.length === 1 ? 'disciplina' : 'disciplinas'} selecionada{formData.subject_ids.length !== 1 ? 's' : ''}
              </CBadge>
            </div>
          </div>

          <CModalFooter className="px-0 mt-4 border-0 pb-0">
            <CButton color="secondary" variant="outline" onClick={handlePreviousStep}>
              <CIcon icon={cilArrowLeft} className="me-2" /> Anterior
            </CButton>
            <CButton color="secondary" variant="ghost" onClick={onCancel}>
              Cancelar
            </CButton>
            <CButton color="primary" onClick={() => setStep(3)}>
              Próximo: Turmas <CIcon icon={cilArrowRight} className="ms-2" />
            </CButton>
          </CModalFooter>
        </>
      )}

      {/* PASSO 3: CONFIGURAÇÃO DE TURMAS */}
      {step === 3 && (
        <div className="animate-fade-in">
          <div className="mb-3 pb-3 border-bottom">
            <h5 className="mb-0">
              <span className="badge bg-primary me-2">3</span>
              Gerar Turmas Iniciais
            </h5>
            <small className="text-muted">Configure as turmas e o ciclo de anos (ex: 2025-2028). Opcional.</small>
          </div>

          {/* ERRO DO PASSO 3 - Renderizado aqui! */}
          {classError && (
            <CAlert color="danger" dismissible onClose={() => setClassError(null)} className="mb-3">
              <strong>⚠️ Erro:</strong> {classError}
            </CAlert>
          )}

          <CCard className="mb-3 bg-light border-0">
            <CCardBody className="p-3">
              {/* Linha 1: Nome e Ano Escolar */}
              <CRow className="g-2 align-items-end mb-2">
                <CCol xs={8}>
                  <label className="form-label small mb-1">Nome Turma <span className="text-danger">*</span></label>
                  <CFormInput 
                    size="sm" 
                    placeholder="Ex: 10º TGEI" 
                    value={newClass.name}
                    onChange={(e) => handleClassInputChange('name', e.target.value)}
                    className={classError && classError.includes('Nome') ? 'is-invalid' : ''}
                  />
                </CCol>
                <CCol xs={4}>
                  <label className="form-label small mb-1">Ano (10-12) <span className="text-danger">*</span></label>
                  <CFormInput 
                    size="sm" 
                    type="number" 
                    min="10" max="12"
                    value={newClass.grade_level}
                    onChange={(e) => handleClassInputChange('grade_level', e.target.value)}
                    className={classError && classError.includes('Ano escolar') ? 'is-invalid' : ''}
                  />
                </CCol>
              </CRow>

              {/* Linha 2: Anos de Calendário (Start/End) - COM VALIDAÇÃO */}
              <CRow className="g-2 align-items-end">
                <CCol xs={4}>
                  <label className="form-label small mb-1">Início (ex: 2025) <span className="text-danger">*</span></label>
                  <CFormInput 
                    size="sm" 
                    type="number" 
                    placeholder="2025"
                    value={newClass.start_year}
                    onChange={(e) => handleClassInputChange('start_year', e.target.value)}
                    className={classError && (classError.includes('início') || classError.includes('Ano de início')) ? 'is-invalid' : ''}
                  />
                  <div className="form-text text-xs">Ano do primeiro ano do ciclo</div>
                </CCol>
                <CCol xs={4}>
                  <label className="form-label small mb-1">Fim (ex: 2028) <span className="text-danger">*</span></label>
                  <CFormInput 
                    size="sm" 
                    type="number" 
                    placeholder="2028"
                    value={newClass.end_year}
                    onChange={(e) => handleClassInputChange('end_year', e.target.value)}
                    className={classError && (classError.includes('fim') || classError.includes('Ano de fim') || classError.includes('maior')) ? 'is-invalid' : ''}
                  />
                  <div className="form-text text-xs">Ano da conclusão esperada</div>
                </CCol>
                <CCol xs={4}>
                  <CButton 
                    color="success" 
                    size="sm" 
                    className="text-white w-100" 
                    onClick={addClassConfig}
                  >
                    <CIcon icon={cilPlus} className="me-1" /> Adicionar
                  </CButton>
                </CCol>
              </CRow>
            </CCardBody>
          </CCard>

          {/* Lista de Turmas Configuradas */}
          {formData.classes_config.length > 0 ? (
            <div className="mb-3">
              <h6 className="mb-2 text-success">✓ {formData.classes_config.length} turma{formData.classes_config.length !== 1 ? 's' : ''} configurada{formData.classes_config.length !== 1 ? 's' : ''}</h6>
              <ul className="list-group text-sm">
                {formData.classes_config.map((cls, idx) => (
                  <li key={idx} className="list-group-item d-flex justify-content-between align-items-center py-2">
                    <div>
                      <span className="fw-bold d-block">{cls.name}</span> 
                      <span className="text-muted small">
                        {cls.grade_level}º Ano ({cls.start_year}-{cls.end_year}) • {cls.size} alunos
                      </span>
                    </div>
                    <CButton color="danger" variant="ghost" size="sm" onClick={() => removeClassConfig(idx)}>
                      <CIcon icon={cilTrash} />
                    </CButton>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <CAlert color="info" className="text-center py-2 text-muted small">
              ℹ️ Sem turmas. O curso será criado apenas como estrutura curricular (pode adicionar turmas depois).
            </CAlert>
          )}

          <CModalFooter className="px-0 mt-4 border-0 pb-0">
            <CButton color="secondary" variant="outline" onClick={() => setStep(2)}>
              <CIcon icon={cilArrowLeft} className="me-2" /> Anterior
            </CButton>
            <CButton color="secondary" variant="ghost" onClick={onCancel}>
              Cancelar
            </CButton>
            <CButton color="success" type="submit" disabled={isLoading} className="text-white">
              {isLoading ? (
                <>
                  <span className="spinner-border spinner-border-sm me-2"></span>
                  A processar...
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

export default CourseForm

