import React, { useState, useEffect } from 'react'
import {
  CForm, CCol, CRow, CFormInput, CButton, CModalFooter, 
  CFormCheck, CFormSwitch, CListGroup, CListGroupItem, CSpinner
} from '@coreui/react'
import { useSubjects } from '../../hooks/useSchoolData'
import PropTypes from 'prop-types'

const TeacherForm = ({ initialData, onSubmit, isLoading, onCancel }) => {
  // 1. Estado Unificado (Removemos o 'createUser' separado)
  const [formData, setFormData] = useState({ 
    name: '', 
    email: '',
    password: '',
    create_user_account: false,
    subject_ids: []
  })

  // 2. Carregar Disciplinas da API (O "Combustível" que faltava)
  const { data: subjects, isLoading: subjectsLoading } = useSubjects()

  // 3. Inicialização dos Dados
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (initialData) {
      let normalizedIds = [];
      if (initialData.subject_ids && Array.isArray(initialData.subject_ids)) {
        normalizedIds = initialData.subject_ids;
      } else if (initialData.subjects && Array.isArray(initialData.subjects)) {
        normalizedIds = initialData.subjects.map(s => s.id);
      }

      setFormData({
        name: initialData.name || '',
        email: initialData.login_email || initialData.email || '', 
        password: '',
        create_user_account: !!initialData.login_email, 
        subject_ids: normalizedIds
      })
    } else {
      // Reset para Criação
      setFormData({ 
        name: '', 
        email: '', 
        password: '',
        create_user_account: false,
        subject_ids: []
      })
    }
  }, [initialData])
  /* eslint-enable react-hooks/set-state-in-effect */

  // --- HANDLERS ---

  // Lida com texto e switches
  const handleChange = (e) => {
    const { name, value, type, checked } = e.target
    setFormData(prev => ({
      ...prev,
      // Se for checkbox/switch usa 'checked', se for texto usa 'value'
      [name]: type === 'checkbox' ? checked : value
    }))
  }

  // Lida especificamente com a seleção de Disciplinas
  const handleSubjectToggle = (subjectId) => {
    setFormData(prev => {
      const currentIds = prev.subject_ids
      if (currentIds.includes(subjectId)) {
        // Se já existe, remove
        return { ...prev, subject_ids: currentIds.filter(id => id !== subjectId) }
      } else {
        // Se não existe, adiciona
        return { ...prev, subject_ids: [...currentIds, subjectId] }
      }
    })
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    onSubmit(formData)
  }

  const renderSubjectsList = () => {
    if (subjectsLoading) return <div className="text-center p-3"><CSpinner size="sm"/></div>
    if (subjects && subjects.length > 0) {
      return (
        <CListGroup flush>
          {subjects.map(sub => (
            <CListGroupItem key={sub.id} className="border-0 py-1">
              <CFormCheck
                id={`sub-${sub.id}`}
                label={sub.name}
                checked={formData.subject_ids.includes(sub.id)}
                onChange={() => handleSubjectToggle(sub.id)}
              />
            </CListGroupItem>
          ))}
        </CListGroup>
      )
    }
    return (
      <div className="text-muted text-center small p-3">
        Não há disciplinas criadas. Vá ao menu “Disciplinas” primeiro.
      </div>
    )
  }

  return (
    <CForm onSubmit={handleSubmit}>
      <CRow className="g-3">
        
        {/* LADO ESQUERDO: Dados do Professor */}
        <CCol md={6}>
          <div className="mb-3">
            <CFormInput
              id="teacher-name"
              label="Nome Completo"
              name="name"
              value={formData.name}
              onChange={handleChange}
              required
              placeholder="Ex: João Silva"
            />
          </div>

          <div className="mb-3 p-3 border rounded bg-light">
            <CFormSwitch 
              label="Criar conta de acesso?"
              name="create_user_account"
              id="createUserAccount"
              checked={formData.create_user_account}
              onChange={handleChange}
              // Se já estamos a editar e ele tem conta, podemos querer manter ativo ou deixar desativar
            />
            <small className="text-muted d-block mt-1">
              Se ativo, o professor poderá fazer login na plataforma.
            </small>
          </div>

          <div className="mb-3">
            <CFormInput
              id="teacher-email"
              type="email"
              // Email é SEMPRE obrigatório agora (cada professor tem uma conta User)
              label="Email de Login (Obrigatório)"
              name="email"
              value={formData.email}
              onChange={handleChange}
              required
              placeholder="joao@escola.pt"
              feedback="Por favor, introduza um email válido."
            />
            <small className="text-muted d-block mt-1">
              Este email será usado para criar a conta de acesso (ativo ou inativo).
            </small>
          </div>

          {formData.create_user_account && (
            <div className="mb-3">
              <CFormInput
                id="teacher-password"
                type="password"
                label={initialData ? 'Nova Password (deixe vazio para não alterar)' : 'Password de Acesso'}
                name="password"
                value={formData.password}
                onChange={handleChange}
                required={!initialData}
                placeholder={initialData ? '••••••••' : 'Mínimo 6 caracteres'}
                autoComplete="new-password"
              />
              <small className="text-muted d-block mt-1">
                O professor usará esta password para entrar na plataforma.
              </small>
            </div>
          )}
        </CCol>

        {/* LADO DIREITO: Lista de Disciplinas (Competências) */}
        <CCol md={6}>
          <p className="form-label fw-bold mb-0">Competências Pedagógicas</p>
          <p className="text-muted small mb-2">Selecione as disciplinas que este professor pode lecionar:</p>
          
          <div className="border rounded p-2" style={{ maxHeight: '300px', overflowY: 'auto' }}>
            {renderSubjectsList()}
          </div>
          
          <div className="mt-2 text-end">
            <small className="text-info">
              {formData.subject_ids.length} disciplina(s) selecionada(s)
            </small>
          </div>
        </CCol>

      </CRow>

      <CModalFooter className="px-0 mt-4 border-top-0">
        <CButton color="secondary" variant="ghost" onClick={onCancel}>
          Cancelar
        </CButton>
        <CButton color="primary" type="submit" disabled={isLoading}>
          {isLoading ? <CSpinner size="sm" component="span" aria-hidden="true" /> : 'Guardar Professor'}
        </CButton>
      </CModalFooter>
    </CForm>
  )
}

TeacherForm.propTypes = {
  initialData: PropTypes.shape({
    name: PropTypes.string,
    email: PropTypes.string,
    login_email: PropTypes.string,
    create_user_account: PropTypes.bool,
    subject_ids: PropTypes.array,
    subjects: PropTypes.array,
  }),
  onSubmit: PropTypes.func.isRequired,
  isLoading: PropTypes.bool,
  onCancel: PropTypes.func.isRequired,
}

export default TeacherForm
