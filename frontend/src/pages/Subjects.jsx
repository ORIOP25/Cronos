import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import PageHeader from '../components/PageHeader'
import { CButton, CAlert } from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilPlus } from '@coreui/icons'

import SmartTable from '../components/SmartTable'
import GenericModalForm from '../components/GenericModalForm'
import SubjectForm from '../components/Forms/SubjectForm'
import RoomTypeBadge from '../components/RoomTypeBadge'
import { getApiErrorMessage } from '../utils/apiErrors'

// Hooks de Dados
import {
  useSubjects,
  useCreateSubject,
  useUpdateSubject,
  useDeleteSubject,
} from '../features/catalog/data'

const Subjects = ({ readOnly = false, allowedActions }) => {
  const navigate = useNavigate()
  const [modalVisible, setModalVisible] = useState(false)
  const [selectedItem, setSelectedItem] = useState(null)

  // 1. Acesso aos Dados
  const { data: subjects, isLoading, isError, error, refetch } = useSubjects()
  const createMutation = useCreateSubject()
  const updateMutation = useUpdateSubject()
  const deleteMutation = useDeleteSubject()
  const isTutorial = Array.isArray(allowedActions)
  const canUpdate = !readOnly && (!isTutorial || allowedActions.includes('UPDATE_SUBJECT'))
  const canOpenDetails = canUpdate || readOnly
  const canCreate = !isTutorial && !readOnly
  const canDelete = !isTutorial && !readOnly

  // 2. Definição das Colunas
  const columns = [
    { key: 'name', label: 'Disciplina' },
    { key: 'required_room_type', label: 'Requisito de Sala', render: (subject) => <RoomTypeBadge type={subject.required_room_type} /> }
  ]

  // --- Handlers ---

  const handleCreate = () => {
    if (!canCreate) return
    // Wizard: Sempre começa do zero (Opção A - Decisão Arquitetural)
    setSelectedItem(null)
    setModalVisible(true)
  }

  const handleEdit = (item) => {
    if (!canOpenDetails) return
    // RESTRIÇÃO: Por enquanto, edição simples (Fase 6)
    // O Wizard é apenas para CRIAÇÃO (Opção A)
    setSelectedItem(item)
    setModalVisible(true)
  }

  const handleDelete = (id) => canDelete ? deleteMutation.mutateAsync(id) : Promise.resolve()

  const handleFormSubmit = async (formData) => {
    try {
      if (selectedItem) {
        await updateMutation.mutateAsync({ id: selectedItem.id, ...formData })
      } else {
        await createMutation.mutateAsync(formData)
      }
      setModalVisible(false)
      // Invalidar cache de cursos (incluem dados de disciplinas/módulos)
    } catch {
      // Erro é tratado pelo mutation (mostrado no GenericModalForm)
    }
  }

  const activeMutation = selectedItem ? updateMutation : createMutation

  return (
    <div className="p-4">
      <PageHeader preTitle="Gestão" title="Disciplinas" />
      {canCreate && <div className="d-flex justify-content-end gap-2 mb-4">
        <CButton color="secondary" variant="outline" onClick={() => navigate('/imports?resource=subjects')}>Importar CSV</CButton>
        <CButton color="primary" onClick={handleCreate} className="d-flex align-items-center gap-2" data-tutorial-target="new-subject">
          <CIcon icon={cilPlus} />
          Nova Disciplina
        </CButton>
      </div>}

      {/* Tratamento de Erros de Criação/Eliminação */}
      {createMutation.isError && (
        <CAlert color="danger" dismissible onClose={createMutation.reset}>
          <strong>Erro ao criar:</strong> {getApiErrorMessage(createMutation.error, 'Erro desconhecido.')}
        </CAlert>
      )}

      {deleteMutation.isError && (
        <CAlert color="danger" dismissible onClose={deleteMutation.reset}>
          <strong>Erro ao remover:</strong> {getApiErrorMessage(deleteMutation.error, 'Erro de dependência.')}
        </CAlert>
      )}

      <SmartTable
            columns={columns}
            data={subjects || []}
            isLoading={isLoading}
            isError={isError}
            error={error}
            onRetry={() => refetch()}
            actions={true}
            onEdit={handleEdit}
            onDelete={handleDelete}
            allowEdit={canOpenDetails}
            allowDelete={canDelete}
            readOnly={readOnly}
            getRowLabel={(subject) => subject.name}
            deleteMessage="Remover esta disciplina? As associações a turmas e cursos serão retiradas e o histórico de horários e progresso será preservado. Se estiver no horário atual, a remoção é bloqueada."
          />

      {/* MODAL COM WIZARD (Opção A: Criação com módulos) */}
      <GenericModalForm
        visible={modalVisible}
        onClose={() => setModalVisible(false)}
        title="Disciplina"
        initialData={selectedItem}
        FormComponent={SubjectForm}
        onSubmit={handleFormSubmit}
        isLoading={activeMutation.isPending}
        error={activeMutation.error}
        tutorialTarget="subject-form"
        readOnly={readOnly}
      />
    </div>
  )
}

export default Subjects
