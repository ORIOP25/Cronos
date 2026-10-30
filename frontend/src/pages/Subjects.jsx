import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'react-hot-toast'
import PageHeader from '../components/PageHeader'
import { CButton } from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilPlus } from '@coreui/icons'

import SmartTable from '../components/SmartTable'
import GenericModalForm from '../components/GenericModalForm'
import SubjectForm from '../components/Forms/SubjectForm'
import RoomTypeBadge from '../components/RoomTypeBadge'
import { getApiErrorMessage } from '../utils/apiErrors'
import { useAttemptScope } from '../hooks/useAttemptScope'

// Hooks de Dados
import {
  useSubjects,
  useCreateSubject,
  useUpdateSubject,
  useDeleteSubject,
} from '../features/catalog/data'

const NEW_MODULE_WARNING = 'Disciplina atualizada. Os módulos novos não foram marcados nas turmas. Marque-os nas turmas que os vão ter.'
const SUBJECT_REMOVAL_EFFECTS = 'As associações a turmas e cursos serão retiradas e o histórico de horários e progresso será preservado. Se estiver no horário atual, a remoção é bloqueada.'

const Subjects = ({ readOnly = false, allowedActions }) => {
  const navigate = useNavigate()
  const [modalVisible, setModalVisible] = useState(false)
  const [selectedItem, setSelectedItem] = useState(null)

  // 1. Acesso aos Dados
  const { data: subjects, isLoading, isError, error, refetch } = useSubjects()
  const createMutation = useCreateSubject()
  const updateMutation = useUpdateSubject()
  const deleteMutation = useDeleteSubject()
  const attemptScope = useAttemptScope()
  const isTutorial = Array.isArray(allowedActions)
  const canUpdate = !readOnly && (!isTutorial || allowedActions.includes('UPDATE_SUBJECT'))
  const canOpenDetails = canUpdate || readOnly
  const canCreate = !isTutorial && !readOnly
  const canDelete = !isTutorial && !readOnly

  // 2. Definição das Colunas
  const columns = [
    { key: 'name', label: 'Disciplina' },
    { key: 'room_type', label: 'Tipo de sala', render: (subject) => <RoomTypeBadge roomType={subject.room_type} /> }
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
    const attempt = attemptScope.capture()
    try {
      if (selectedItem) {
        await updateMutation.mutateAsync({ id: selectedItem.id, ...formData })
        if (!attemptScope.isCurrent(attempt)) return
        const addsModule = (formData.modules || []).some((module) => module.id == null)
        toast.success(addsModule ? NEW_MODULE_WARNING : 'Disciplina atualizada.')
      } else {
        await createMutation.mutateAsync(formData)
        if (!attemptScope.isCurrent(attempt)) return
        toast.success('Disciplina criada.')
      }
      setModalVisible(false)
    } catch (error) {
      if (!attemptScope.isCurrent(attempt)) return
      toast.error(getApiErrorMessage(error, 'Não foi possível guardar a disciplina. Tente novamente.'))
    }
  }

  const activeMutation = selectedItem ? updateMutation : createMutation

  return (
    <div className="p-4">
      <PageHeader title="Disciplinas">
      {canCreate && <>
        <CButton color="secondary" variant="outline" onClick={() => navigate('/imports?resource=subjects')}>Importar CSV</CButton>
        <CButton color="primary" onClick={handleCreate} className="d-flex align-items-center gap-2" data-tutorial-target="new-subject">
          <CIcon icon={cilPlus} />
          Nova disciplina
        </CButton>
      </>}
      </PageHeader>

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
            deleteMessage={`Remover esta disciplina? ${SUBJECT_REMOVAL_EFFECTS}`}
            bulkDeleteMessage={SUBJECT_REMOVAL_EFFECTS}
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
        tutorialTarget="subject-form"
        readOnly={readOnly}
      />
    </div>
  )
}

export default Subjects
