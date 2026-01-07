import React, { useState, useEffect } from 'react'
import {
  CForm, CCol, CRow, CFormInput, CButton, CModalFooter, CFormCheck
} from '@coreui/react'

const TeacherForm = ({ initialData, onSubmit, isLoading, onCancel }) => {
  // Estado local do formulário
  const [formData, setFormData] = useState({ 
    name: '', 
    email: '' 
  })
  
  // Estado para a opção de criar conta (Apenas relevante na criação)
  const [createUser, setCreateUser] = useState(true)

  // Popula o formulário se estivermos em modo de Edição
  useEffect(() => {
    if (initialData) {
      setFormData({
        name: initialData.name || '',
        email: initialData.email || ''
      })
      // Na edição, ignoramos a criação de user para já
    } else {
        // Reset para criação
        setFormData({ name: '', email: '' })
        setCreateUser(true) // Por defeito, queremos criar conta
    }
  }, [initialData])

  const handleChange = (e) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    
    // Prepara o objeto final
    const finalData = {
        ...formData,
        // Se for criação (!initialData), enviamos a flag create_user_account
        ...( !initialData && { create_user_account: createUser } )
    }

    // Envia os dados para o componente pai (o Modal)
    onSubmit(finalData)
  }

  return (
    <CForm onSubmit={handleSubmit}>
      <CRow className="g-3">
        <CCol md={12}>
          <CFormInput
            type="text"
            label="Nome Completo"
            name="name"
            value={formData.name}
            onChange={handleChange}
            required
            placeholder="Ex: Maria Silva"
          />
        </CCol>
        
        <CCol md={12}>
          <CFormInput
            type="email"
            label="Email Institucional"
            name="email"
            value={formData.email}
            onChange={handleChange}
            placeholder="Ex: maria.silva@escola.pt"
            text={initialData ? "" : "Obrigatório para criar conta de acesso."}
          />
        </CCol>

        {/* Checkbox de Criação de Conta (Apenas Visível no Modo Criação) */}
        {!initialData && (
            <CCol md={12} className="pt-2">
                <div className="bg-light p-3 rounded border">
                    <CFormCheck 
                        id="createUserCheck"
                        label="Criar conta de acesso à plataforma?"
                        checked={createUser}
                        onChange={(e) => setCreateUser(e.target.checked)}
                        disabled={!formData.email} // Só ativa se houver email
                    />
                    <small className="text-muted d-block mt-1">
                        Se marcado, o professor receberá acesso com este email. A password será gerada automaticamente ou definida por defeito (ex: 'mudar123').
                    </small>
                </div>
            </CCol>
        )}
      </CRow>

      {/* Footer do Formulário (Botões de Ação) */}
      <CModalFooter className="px-0 mt-4 border-0 pb-0">
        <CButton color="secondary" variant="ghost" onClick={onCancel}>
          Cancelar
        </CButton>
        <CButton color="primary" type="submit" disabled={isLoading}>
          {isLoading ? 'A gravar...' : (initialData ? 'Atualizar Professor' : 'Criar Professor')}
        </CButton>
      </CModalFooter>
    </CForm>
  )
}

export default TeacherForm