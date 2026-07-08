import React, { useState } from 'react'
import PageHeader from '../components/PageHeader'
import { CCard, CCardBody, CButton, CAlert } from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilPlus, cilSync } from '@coreui/icons'

import SmartTable from '../components/SmartTable'
import GenericModalForm from '../components/GenericModalForm'
import TimeslotForm from '../components/Forms/TimeslotForm'
import TimeslotGeneratorModal from '../components/Modals/TimeslotGeneratorModal'
import { getApiErrorMessage } from '../utils/apiErrors'

import { 
  useTimeslots, 
  useCreateEntity, 
  useUpdateEntity, 
  useDeleteEntity 
} from '../hooks/useSchoolData'

const Timeslots = () => {
  const [modalVisible, setModalVisible] = useState(false)
  const [selectedItem, setSelectedItem] = useState(null)
  const [genModalVisible, setGenModalVisible] = useState(false)

  const { data: timeslots, isLoading, isError, error, refetch } = useTimeslots()
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
      <PageHeader preTitle="Configuração" title={<span>Blocos <span className="text-editorial">Horários</span></span>} />
      
      <div className="d-flex justify-content-between align-items-center mb-4 flex-wrap gap-3">
        <div></div>
        <div className="d-flex gap-2">
          
          {/* ALTERAÇÃO 2: O Novo Botão "Gerar Auto" */}
          <CButton color="success" variant="outline" onClick={() => setGenModalVisible(true)}>
             <CIcon icon={cilSync} size="sm" className="me-1" /> Gerar Auto
          </CButton>

          <CButton color="primary" onClick={handleCreate} className="d-flex align-items-center gap-2">
            <CIcon icon={cilPlus} />
            Novo Bloco
          </CButton>
        </div>
      </div>

      {/* Tratamento de Erros ROBUSTO */}
      {deleteMutation.isError && (
        <CAlert color="danger" dismissible onClose={deleteMutation.reset}>
          <strong>Erro ao remover:</strong> {getApiErrorMessage(deleteMutation.error)}
        </CAlert>
      )}

      <CCard className="border-0 shadow-sm">
        <CCardBody className="p-0">
          <SmartTable
            columns={columns}
            data={tableData}
            isLoading={isLoading}
            isError={isError}
            error={error}
            onRetry={() => refetch()}
            actions={true}
            onEdit={handleEdit}
            onDelete={handleDelete}
          />
        </CCardBody>
      </CCard>

      {/* ALTERAÇÃO 3: Renderizar o Modal de Geração (Pode ficar aqui, antes do outro modal) */}
      <TimeslotGeneratorModal 
        visible={genModalVisible} 
        onClose={() => setGenModalVisible(false)} 
      />

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
