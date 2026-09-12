import { useMemo, useState } from 'react'
import {
  CAlert,
  CBadge,
  CButton,
  CFormCheck,
  CFormInput,
  CFormSelect,
  CFormSwitch,
  CModal,
  CModalBody,
  CModalFooter,
  CModalHeader,
  CModalTitle,
  CSpinner,
  CTooltip,
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilActionUndo, cilPencil, cilPlus, cilReload, cilTrash } from '@coreui/icons'
import PageHeader from '../components/PageHeader'
import { getApiErrorMessage } from '../utils/apiErrors'
import {
  useCreateMember,
  useMembers,
  useRemoveMember,
  useResendMemberInvitation,
  useRestoreMember,
  useRetryMemberSync,
  useUpdateMember,
} from '../features/members/data'
import { useSubjects } from '../features/catalog/data'
import ConfirmationModal from '../components/ConfirmationModal'

const emptyDraft = {
  organization_display_name: '',
  email: '',
  capability_mode: 'teacher',
  teacher_access_mode: 'scheduler_only',
  subject_ids: [],
}

const restorePayloadFromMember = (member) => ({
  restore_access: member.expected_clerk_role !== null,
  capabilities: member.capabilities,
  teacher_access_mode: member.teacher_access_mode,
  subject_ids: member.subject_ids ?? [],
})

const accessLabels = {
  none: ['Sem acesso', 'secondary'],
  pending_invite: ['Convite pendente', 'warning'],
  invite_expired: ['Convite expirado', 'warning'],
  active: ['Com acesso', 'success'],
  blocked: ['Acesso bloqueado', 'dark'],
  sync_error: ['Erro de sincronizacao', 'danger'],
}

const lifecycleLabels = {
  active: ['Ativo', 'success'],
  archived: ['Arquivado', 'secondary'],
}

const modeToCapabilities = (mode) => (mode === 'mixed' ? ['teacher', 'admin'] : [mode])
const capabilitiesToMode = (capabilities = []) => {
  if (capabilities.includes('teacher') && capabilities.includes('admin')) return 'mixed'
  if (capabilities.includes('admin')) return 'admin'
  return 'teacher'
}

const SubjectPicker = ({ subjects, selected, disabled, onChange }) => {
  if (!subjects?.length) return <div className="text-muted small">Sem competencias registadas.</div>
  const toggle = (subjectId) => {
    const next = selected.includes(subjectId)
      ? selected.filter((id) => id !== subjectId)
      : [...selected, subjectId]
    onChange(next)
  }
  return (
    <div className="border rounded p-3" style={{ maxHeight: 220, overflowY: 'auto' }}>
      {subjects.map((subject) => (
        <CFormCheck
          key={subject.id}
          id={`member-subject-${subject.id}`}
          label={subject.name}
          checked={selected.includes(subject.id)}
          disabled={disabled}
          onChange={() => toggle(subject.id)}
        />
      ))}
    </div>
  )
}

const MemberModal = ({ visible, member, subjects, onClose, onSave, isSaving, error, competenciesOnly = false }) => {
  const [draft, setDraft] = useState(() => member ? {
    organization_display_name: member.organization_display_name ?? '',
    email: member.email ?? '',
    capability_mode: capabilitiesToMode(member.capabilities),
    teacher_access_mode: member.teacher_access_mode ?? 'scheduler_only',
    subject_ids: member.subject_ids ?? [],
    lock_version: member.lock_version,
  } : emptyDraft)
  const [adminConfirmed, setAdminConfirmed] = useState(false)

  const hasTeacher = draft.capability_mode === 'teacher' || draft.capability_mode === 'mixed'
  const hasAdmin = draft.capability_mode === 'admin' || draft.capability_mode === 'mixed'
  const syncBlocked = member?.access_status === 'sync_error'
  const adminRequiresConfirmation = hasAdmin && !adminConfirmed

  const submit = () => {
    if (adminRequiresConfirmation) return
    const payload = {
      organization_display_name: draft.organization_display_name,
      email: draft.email,
      capabilities: modeToCapabilities(draft.capability_mode),
      subject_ids: hasTeacher ? draft.subject_ids : [],
    }
    if (hasTeacher) payload.teacher_access_mode = hasAdmin ? 'platform' : draft.teacher_access_mode
    if (member) {
      payload.id = member.id
      payload.lock_version = draft.lock_version
    }
    onSave(payload)
  }

  return (
    <CModal visible={visible} onClose={onClose} alignment="center" size="lg" className="app-modal" data-tutorial-target="member-form">
      <CModalHeader>
        <CModalTitle>{member ? 'Editar membro' : 'Adicionar membro'}</CModalTitle>
      </CModalHeader>
      <CModalBody>
        {error && <CAlert color="danger">{getApiErrorMessage(error)}</CAlert>}
        {syncBlocked && <CAlert color="warning">Resolva a sincronizacao antes de editar este membro.</CAlert>}
        <div className="d-grid gap-3">
          <CFormInput id="member-name" label="Nome" value={draft.organization_display_name} onChange={(event) => setDraft({ ...draft, organization_display_name: event.target.value })} disabled={isSaving || syncBlocked || competenciesOnly} />
          <CFormInput id="member-email" label="Email" type="email" value={draft.email} onChange={(event) => setDraft({ ...draft, email: event.target.value })} disabled={isSaving || syncBlocked || member?.access_status === 'active' || competenciesOnly} />
          <CFormSelect
            id="member-capability-mode"
            label="Tipo de membro"
            value={draft.capability_mode}
            onChange={(event) => {
              setAdminConfirmed(false)
              setDraft({ ...draft, capability_mode: event.target.value, teacher_access_mode: event.target.value === 'admin' ? 'platform' : draft.teacher_access_mode })
            }}
            disabled={isSaving || syncBlocked || competenciesOnly}
            options={[
              { value: 'teacher', label: 'Professor' },
              { value: 'admin', label: 'Administrador' },
              { value: 'mixed', label: 'Professor + Administrador' },
            ]}
          />
          {hasTeacher && (
            <>
              <CFormSelect
                id="member-teacher-access-mode"
                label="Acesso do professor"
                value={hasAdmin ? 'platform' : draft.teacher_access_mode}
                onChange={(event) => setDraft({ ...draft, teacher_access_mode: event.target.value })}
                disabled={isSaving || syncBlocked || hasAdmin || competenciesOnly}
                options={[
                  { value: 'platform', label: 'Com acesso a plataforma' },
                  { value: 'scheduler_only', label: 'Apenas recurso de horario' },
                ]}
              />
              {draft.teacher_access_mode === 'scheduler_only' && !hasAdmin && (
                <CAlert color="info" className="mb-0">
                  Este professor fica disponivel para horarios, mas nao recebe convite nem acesso para iniciar sessao.
                </CAlert>
              )}
              <SubjectPicker subjects={subjects} selected={draft.subject_ids} disabled={isSaving || syncBlocked} onChange={(subject_ids) => setDraft({ ...draft, subject_ids })} />
            </>
          )}
          {hasAdmin && (
            <CFormCheck
              id="member-admin-confirmation"
              label="Confirmo que este membro deve ter acesso de administrador."
              checked={adminConfirmed}
              disabled={isSaving || syncBlocked || competenciesOnly}
              onChange={(event) => setAdminConfirmed(event.target.checked)}
            />
          )}
        </div>
      </CModalBody>
      <CModalFooter>
        <CButton color="secondary" variant="outline" onClick={onClose} disabled={isSaving}>Cancelar</CButton>
        <CButton color="primary" onClick={submit} disabled={isSaving || syncBlocked || adminRequiresConfirmation}>
          {isSaving && <CSpinner size="sm" className="me-2" />}Guardar
        </CButton>
      </CModalFooter>
    </CModal>
  )
}

const ActionButton = ({ title, color = 'secondary', icon, disabled, loading, onClick, tutorialTarget }) => {
  const isDisabled = disabled || loading
  return (
    <CTooltip content={title} placement="top">
      <span className="member-action-tooltip" title={title} tabIndex={isDisabled ? 0 : undefined}>
        <CButton color={color} variant="ghost" size="sm" onClick={onClick} aria-label={title} disabled={isDisabled} data-tutorial-target={tutorialTarget}>
          {loading ? <CSpinner size="sm" /> : <CIcon icon={icon} />}
        </CButton>
      </span>
    </CTooltip>
  )
}

const Members = ({ readOnly = false, allowedActions }) => {
  const [includeArchived, setIncludeArchived] = useState(false)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [selectedMember, setSelectedMember] = useState(null)
  const [modalVisible, setModalVisible] = useState(false)
  const [removeTarget, setRemoveTarget] = useState(null)
  const { data, isLoading, isError, error, refetch } = useMembers({ includeArchived })
  const { data: subjects = [] } = useSubjects()
  const createMember = useCreateMember()
  const updateMember = useUpdateMember()
  const removeMember = useRemoveMember()
  const resendInvitation = useResendMemberInvitation()
  const retrySync = useRetryMemberSync()
  const restoreMember = useRestoreMember()
  const isTutorial = Array.isArray(allowedActions)
  const canUpdate = !readOnly && (!isTutorial || allowedActions.includes('UPDATE_MEMBER_COMPETENCIES'))
  const canCreate = !readOnly && !isTutorial
  const activeMutation = selectedMember ? updateMember : createMember
  const members = useMemo(() => {
    const rows = data?.items ?? []
    const normalizedSearch = search.trim().toLowerCase()
    return rows.filter((member) => {
      const matchesSearch = !normalizedSearch
        || member.organization_display_name.toLowerCase().includes(normalizedSearch)
        || member.email.toLowerCase().includes(normalizedSearch)
      const matchesStatus = statusFilter === 'all'
        || member.access_status === statusFilter
        || member.lifecycle_status === statusFilter
      return matchesSearch && matchesStatus
    })
  }, [data?.items, search, statusFilter])

  const openModal = (member = null) => {
    if (member && !canUpdate) return
    if (!member && !canCreate) return
    setSelectedMember(member)
    setModalVisible(true)
  }

  const save = async (payload) => {
    await activeMutation.mutateAsync(payload)
    setModalVisible(false)
  }

  const remove = async () => {
    if (!removeTarget || !canCreate) return
    await removeMember.mutateAsync(removeTarget.id)
    setRemoveTarget(null)
  }

  const actionErrorSource = removeMember.error || resendInvitation.error || retrySync.error || restoreMember.error
  const actionError = actionErrorSource ? getApiErrorMessage(actionErrorSource) : null

  return (
    <div className="p-4">
      <PageHeader preTitle="Gestão" title="Equipa" />
      <div className="d-flex justify-content-between align-items-center mb-4 gap-3 flex-wrap">
        <div className="d-flex gap-2 flex-wrap">
          <CFormInput
            value={search}
            placeholder="Pesquisar por nome ou email"
            onChange={(event) => setSearch(event.target.value)}
            style={{ minWidth: 260 }}
          />
          <CFormSelect
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            style={{ minWidth: 220 }}
            options={[
              { value: 'all', label: 'Todos os estados' },
              { value: 'active', label: 'Com acesso / ativo' },
              { value: 'pending_invite', label: 'Convite pendente' },
              { value: 'invite_expired', label: 'Convite expirado' },
              { value: 'sync_error', label: 'Erro de sincronizacao' },
              { value: 'blocked', label: 'Acesso bloqueado' },
              { value: 'archived', label: 'Arquivado' },
            ]}
          />
          <CFormSwitch label="Mostrar arquivados" checked={includeArchived} onChange={(event) => setIncludeArchived(event.target.checked)} />
        </div>
        {canCreate && <CButton color="primary" onClick={() => openModal()} className="d-flex align-items-center gap-2" data-tutorial-target="new-member"><CIcon icon={cilPlus} />Adicionar membro</CButton>}
      </div>
      {isError && <CAlert color="danger">{getApiErrorMessage(error, 'Nao foi possivel carregar a equipa.')} <CButton color="link" onClick={() => refetch()}>Tentar novamente</CButton></CAlert>}
      {actionError && <CAlert color="danger">{actionError}</CAlert>}
      <div className="table-responsive">
        <table className="table align-middle">
          <thead><tr><th>Nome</th><th>Email</th><th>Tipo</th><th>Estado</th><th>Competências</th><th className="text-end">Ações</th></tr></thead>
          <tbody>
            {isLoading && <tr><td colSpan="6"><CSpinner size="sm" /> A carregar equipa...</td></tr>}
            {!isLoading && members.map((member) => {
              const [accessLabel, accessColor] = accessLabels[member.access_status] ?? [member.access_status, 'secondary']
              const [lifecycleLabel, lifecycleColor] = lifecycleLabels[member.lifecycle_status] ?? [member.lifecycle_status, 'secondary']
              const providerUnconfirmed = member.provider_state === 'unconfirmed'
              return (
                <tr key={member.id}>
                  <td className="fw-semibold">{member.organization_display_name}</td>
                  <td>{member.email}</td>
                  <td>
                    {member.capabilities.includes('teacher') && <CBadge color="primary" className="me-1">Professor</CBadge>}
                    {member.capabilities.includes('admin') && <CBadge color="dark">Administrador</CBadge>}
                  </td>
                  <td>
                    <CBadge color={lifecycleColor} className="me-1">{lifecycleLabel}</CBadge>
                    <CBadge color={accessColor}>{accessLabel}</CBadge>
                    {providerUnconfirmed && <CBadge color="warning" className="ms-1">Fornecedor por confirmar</CBadge>}
                    {member.access_error_safe_message && <div className="text-danger small mt-1">{member.access_error_safe_message}</div>}
                    {member.access_status === 'pending_invite' && (
                      <div className="text-muted small mt-1">Criado no Clerk; entrega do email por confirmar.</div>
                    )}
                  </td>
                  <td className="small text-muted">
                    {member.capabilities.includes('teacher')
                      ? member.subject_ids?.length ? `${member.subject_ids.length} selecionadas` : 'Sem competencias'
                      : '-'}
                  </td>
                  <td className="text-end">
                    <ActionButton title="Editar membro" icon={cilPencil} disabled={!member.actions?.can_edit || !canUpdate} onClick={() => openModal(member)} tutorialTarget={`edit-member-${member.id}`} />
                    <ActionButton title="Reenviar convite" icon={cilReload} disabled={isTutorial || !member.actions?.can_resend_invite} loading={resendInvitation.isPending} onClick={() => resendInvitation.mutate(member.id)} />
                    <ActionButton title="Tentar sincronização novamente" icon={cilReload} color="warning" disabled={isTutorial || !member.actions?.can_retry_sync} loading={retrySync.isPending} onClick={() => retrySync.mutate(member.id)} />
                    <ActionButton title="Restaurar membro" icon={cilActionUndo} color="success" disabled={isTutorial || !member.actions?.can_restore} loading={restoreMember.isPending} onClick={() => restoreMember.mutate({ id: member.id, payload: restorePayloadFromMember(member) })} />
                    <ActionButton title="Remover membro" icon={cilTrash} color="danger" disabled={isTutorial || !member.actions?.can_remove} loading={removeMember.isPending} onClick={() => setRemoveTarget(member)} />
                  </td>
                </tr>
              )
            })}
            {!isLoading && members.length === 0 && (
              <tr>
                <td colSpan="6" className="text-muted">
                  {search || statusFilter !== 'all'
                    ? 'Sem membros com estes filtros.'
                    : 'Adicione o primeiro membro da equipa.'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <ConfirmationModal
        visible={Boolean(removeTarget)}
        onClose={() => setRemoveTarget(null)}
        onConfirm={() => void remove()}
        title="Remover membro"
        message={removeTarget?.remove_effect === 'hard_delete'
          ? 'Este membro ainda não tem histórico e será removido definitivamente.'
          : 'Este membro tem histórico e será arquivado para preservar horários, aulas e auditoria.'}
        confirmText="Remover"
        isLoading={removeMember.isPending}
      />
        <MemberModal
        key={`${modalVisible ? 'open' : 'closed'}-${selectedMember?.id ?? 'new'}`}
        visible={modalVisible}
        member={selectedMember}
        subjects={subjects}
        onClose={() => setModalVisible(false)}
        onSave={save}
        isSaving={activeMutation.isPending}
          error={activeMutation.error}
          competenciesOnly={isTutorial}
      />
    </div>
  )
}

export default Members
