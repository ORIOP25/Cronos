import React, { useState } from 'react'
import { 
  CCard, CCardBody, CCol, CRow, CButton, CAlert, CBadge 
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilClock, cilPlus } from '@coreui/icons'

import SmartTable from '../components/SmartTable'
import GenericModalForm from '../components/GenericModalForm'
import TimeslotForm from '../components/Forms/TimeslotForm'

import { 
  useTimeslots, 
  useCreateEntity, 
  useUpdateEntity, 
  useDeleteEntity 
} from '../hooks/useSchoolData'

const Timeslots = () => {
  const [modalVisible, setModalVisible] = useState(false)
  const [selectedItem, setSelectedItem] = useState(null)

  const { data: timeslots, isLoading } = useTimeslots()
  const createMutation = useCreateEntity('timeslots')
  const updateMutation = useUpdateEntity('timeslots')
  const deleteMutation = useDeleteEntity('timeslots')

  const columns = [
    { key: 'day_label', label: 'Dia' },
    { key: 'time_label', label: 'Horário' }
  ]

  // ViewModel: Mapear 0 -> Segunda
  const daysMap = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]

  const tableData = (timeslots || []).map(t => ({
    ...t,
    day_label: <span className="fw-bold">{daysMap[t.day_of_week]}</span>,
    time_label: `${t.start_time.substring(0,5)} - ${t.end_time.substring(0,5)}`
  }))

  const handleCreate = () => {
    setSelectedItem(null)
    setModalVisible(true)
  }

  const handleEdit = (item) => {
    setSelectedItem(item)
    setModalVisible(true)
  }

  const handleDelete = (id) => {
    deleteMutation.mutate(id)
  }

  const handleFormSubmit = async (formData) => {
    if (selectedItem) {
      await updateMutation.mutateAsync({ id: selectedItem.id, ...formData })
    } else {
      await createMutation.mutateAsync(formData)
    }
    setModalVisible(false)
  }

  const activeMutation = selectedItem ? updateMutation : createMutation

  return (
    <div className="p-4">
      <CRow className="mb-4 align-items-center">
        <CCol>
          <h2 className="mb-0 fw-bold text-dark">
            <CIcon icon={cilClock} className="me-2 text-warning" />
            Blocos Horários
          </h2>
          <small className="text-muted">Defina a grelha de tempos (ex: 08:30 - 09:15).</small>
        </CCol>
        <CCol className="text-end">
          <CButton color="primary" onClick={handleCreate} className="d-flex align-items-center gap-2 ms-auto">
            <CIcon icon={cilPlus} />
            Novo Bloco
          </CButton>
        </CCol>
      </CRow>

      {/* Tratamento de Erros ROBUSTO */}
      {deleteMutation.isError && (
        <CAlert color="danger" dismissible onClose={deleteMutation.reset}>
          <strong>Erro ao remover:</strong> {
            (() => {
              // Tenta ler a mensagem detalhada enviada pelo FastAPI
              const detail = deleteMutation.error?.response?.data?.detail;
              
              // Se for uma lista (erros de validação), junta-os
              if (Array.isArray(detail)) {
                  return detail.map(e => e.msg).join(', ');
              }
              
              // Se for string simples (nossos erros manuais), mostra-a
              return detail || "Ocorreu um erro desconhecido.";
            })()
          }
        </CAlert>
      )}

      <CCard className="border-0 shadow-sm">
        <CCardBody className="p-0">
          <SmartTable
            columns={columns}
            data={tableData}
            isLoading={isLoading}
            actions={true}
            onEdit={handleEdit}
            onDelete={handleDelete}
          />
        </CCardBody>
      </CCard>

      <GenericModalForm
        visible={modalVisible}
        onClose={() => setModalVisible(false)}
        title="Bloco Horário"
        initialData={selectedItem}
        FormComponent={TimeslotForm}
        onSubmit={handleFormSubmit}
        isLoading={activeMutation.isPending}
        error={activeMutation.error}
      />
    </div>
  )
}

export default Timeslots