import { useMemo, useState } from 'react'
import { toast } from 'react-hot-toast'
import { useSearchParams } from 'react-router-dom'
import {
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
import FeedbackBanner from '../components/FeedbackBanner'
import { BulkRemovalActions, BulkSelectionCheckbox } from '../components/BulkRemoval'
import { useBulkRemoval } from '../hooks/useBulkRemoval'
import { getApiErrorMessage, isApiErrorTransient } from '../utils/apiErrors'
import { useAttemptScope } from '../hooks/useAttemptScope'
import { TXT } from '../utils/terminology'
import {
  useCreateMember,
  useMembers,
  useRemoveMember,
  useResendMemberInvitation,
  useRestoreMember,
  useRetryMemberSync,
  useTeachers,
  useUpdateMember,
} from '../features/members/data'
import { useSubjects } from '../features/catalog/data'
import ConfirmationModal from '../components/ConfirmationModal'
import TeacherAvailabilityModal from '../components/TeacherAvailabilityModal'

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
  sync_error: ['Acesso por confirmar', 'warning'],
}

const accessErrorMessages = {
  provider_unavailable: 'Não foi possível confirmar o acesso neste momento.',
  provider_not_found: 'Não foi possível confirmar o acesso neste momento.',
  provider_mismatch: 'Os dados de acesso precisam de ser confirmados.',
  provider_role_mismatch: 'Os dados de acesso precisam de ser confirmados.',
  identity_conflict: 'Os dados de acesso precisam de ser confirmados.',
  unknown: 'Não foi possível confirmar o estado de acesso.',
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
  if (!subjects?.length) return <div className="text-muted small">Sem competências registadas.</div>
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

const MemberModal = ({ visible, member, subjects, onClose, onSave, isSaving, error, competenciesOnly = false, canEdit = true, actions, onAvailability, actionVersion }) => {
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
    if (!canEdit || adminRequiresConfirmation || syncBlocked || isSaving) return
    const payload = {
      organization_display_name: draft.organization_display_name,
      email: draft.email,
      capabilities: modeToCapabilities(draft.capability_mode),
      subject_ids: hasTeacher ? draft.subject_ids : [],
    }
    if (hasTeacher) payload.teacher_access_mode = hasAdmin ? 'platform' : draft.teacher_access_mode
    if (member) {
      payload.id = member.id
      payload.lock_version = actionVersion ?? draft.lock_version
    }
    onSave(payload)
  }

  const submitLabel = member ? TXT.SAVE_CHANGES : 'Adicionar membro'

  return (
    <CModal visible={visible} onClose={isSaving || !visible ? undefined : onClose} keyboard={!isSaving} backdrop={isSaving ? 'static' : true} alignment="center" size="lg" className="app-modal" data-tutorial-target="member-form">
      <CModalHeader>
        <CModalTitle>{member ? 'Editar membro' : 'Adicionar membro'}</CModalTitle>
      </CModalHeader>
      <CModalBody>
        {error && (
          <div className="mb-3"><FeedbackBanner tone="danger">{getApiErrorMessage(error, undefined, member ? 'team.sync' : 'team.invite')}</FeedbackBanner></div>
        )}
        {syncBlocked && (
          <div className="mb-3"><FeedbackBanner tone="warning">Confirme primeiro o acesso deste membro para o poder editar.</FeedbackBanner></div>
        )}
        {member && <fieldset disabled={isSaving} className="member-management mb-4" aria-label="Gestão do membro">
          {onAvailability && <CButton color="primary" variant="outline" onClick={onAvailability} disabled={isSaving}>Editar disponibilidade</CButton>}
          {actions}
        </fieldset>}
        <fieldset disabled={!canEdit} className="d-grid gap-3">
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
                  { value: 'scheduler_only', label: 'Apenas horário (sem acesso à plataforma)' },
                ]}
              />
              {draft.teacher_access_mode === 'scheduler_only' && !hasAdmin && (
                <FeedbackBanner tone="info">
                  Este professor fica disponível para horários, mas não recebe convite nem acesso para iniciar sessão.
                </FeedbackBanner>
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
        </fieldset>
      </CModalBody>
      <CModalFooter>
        <CButton color="secondary" variant="outline" onClick={onClose} disabled={isSaving}>Cancelar</CButton>
        <CButton color="primary" onClick={submit} disabled={!canEdit || isSaving || syncBlocked || adminRequiresConfirmation}>
          {isSaving && <CSpinner size="sm" className="me-2" />}{isSaving ? TXT.SAVING : submitLabel}
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
          {loading ? <CSpinner size="sm" /> : <CIcon icon={icon} />}<span className="ms-1">{title}</span>
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
  const [actionVersion, setActionVersion] = useState(null)
  const [modalVisible, setModalVisible] = useState(false)
  const [removeTarget, setRemoveTarget] = useState(null)
  const [searchParams, setSearchParams] = useSearchParams()
  const { data, isLoading, isError, error, refetch } = useMembers({ includeArchived })
  const { data: subjects = [] } = useSubjects()
  const { data: teachers = [] } = useTeachers()
  const availabilityTeacherId = Number.parseInt(searchParams.get('teacher_id') ?? '', 10)
  const showAvailability = searchParams.get('panel') === 'availability'
    && !Number.isNaN(availabilityTeacherId)
  const availabilityTeacher = useMemo(() => {
    if (!showAvailability) return null
    const member = data?.items?.find((item) => item.teacher_id === availabilityTeacherId)
    return teachers.find((teacher) => teacher.id === availabilityTeacherId)
      ?? (member ? { id: member.teacher_id, name: member.organization_display_name } : null)
  }, [showAvailability, teachers, availabilityTeacherId, data])
  const closeAvailability = () => {
    setSearchParams((previous) => {
      const next = new URLSearchParams(previous)
      next.delete('panel')
      next.delete('teacher_id')
      next.delete('on_date')
      return next
    }, { replace: true })
  }
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
  const attemptScope = useAttemptScope()
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

  const removableMembers = canCreate ? members.filter((member) => member.actions?.can_remove).map((member) => ({ ...member, name: member.organization_display_name })) : []
  const bulk = useBulkRemoval(removableMembers, (id) => removeMember.mutateAsync(id))

  const openModal = (member = null) => {
    if (member && !canUpdate) return
    if (!member && !canCreate) return
    setSelectedMember(member)
    setActionVersion(null)
    setModalVisible(true)
  }

  const save = async (payload) => {
    const attempt = attemptScope.capture()
    try {
      await activeMutation.mutateAsync(payload)
      if (!attemptScope.isCurrent(attempt)) return
      setModalVisible(false)
      toast.success(selectedMember ? 'Membro atualizado.' : 'Membro adicionado.')
    } catch (error) {
      if (!attemptScope.isCurrent(attempt)) return
      if (isApiErrorTransient(error)) {
        activeMutation.reset()
        toast.error(getApiErrorMessage(error))
      }
    }
  }

  const remove = async () => {
    if (!removeTarget || !canCreate) return
    const attempt = attemptScope.capture()
    try {
      await removeMember.mutateAsync(removeTarget.id)
      if (!attemptScope.isCurrent(attempt)) return
      setModalVisible(false)
      setSelectedMember(null)
      toast.success(removeTarget.remove_effect === 'hard_delete' ? 'Membro removido.' : 'Membro arquivado.')
    } catch (error) {
      if (!attemptScope.isCurrent(attempt)) return
      if (isApiErrorTransient(error)) {
        removeMember.reset()
        toast.error(getApiErrorMessage(error))
      }
    } finally {
      setRemoveTarget(null)
    }
  }

  const actionErrorSource = removeMember.error || resendInvitation.error || retrySync.error || restoreMember.error
  const actionError = actionErrorSource ? getApiErrorMessage(actionErrorSource) : null

  const handleActionError = (error) => {
    if (isApiErrorTransient(error)) toast.error(getApiErrorMessage(error))
  }

  const managedMember = data?.items?.find((member) => member.id === selectedMember?.id) ?? selectedMember
  const actionSucceeded = (message) => (member) => {
    // Only our own next revision can advance the draft's concurrency token.
    setActionVersion((current) => member.lock_version === (current ?? selectedMember.lock_version) + 1 ? member.lock_version : current)
    toast.success(message)
  }
  const memberActions = (member) => !isTutorial && member && <>
    {member.actions?.can_resend_invite && <ActionButton title="Reenviar convite" icon={cilReload} loading={resendInvitation.isPending} onClick={() => resendInvitation.mutate(member.id, attemptScope.guard({ onSuccess: actionSucceeded('Convite reenviado.'), onError: handleActionError }))} />}
    {member.actions?.can_retry_sync && <ActionButton title="Tentar confirmar o acesso novamente" icon={cilReload} color="warning" loading={retrySync.isPending} onClick={() => retrySync.mutate(member.id, attemptScope.guard({ onSuccess: actionSucceeded('Acesso confirmado.'), onError: handleActionError }))} />}
    {member.actions?.can_restore && <ActionButton title="Restaurar membro" icon={cilActionUndo} color="success" loading={restoreMember.isPending} onClick={() => restoreMember.mutate({ id: member.id, payload: restorePayloadFromMember(member) }, attemptScope.guard({ onSuccess: actionSucceeded('Membro restaurado.'), onError: handleActionError }))} />}
    {member.actions?.can_remove && <ActionButton title="Remover membro" icon={cilTrash} color="danger" loading={removeMember.isPending} onClick={() => setRemoveTarget(member)} />}
  </>

  return (
    <div className="p-4">
      <PageHeader preTitle="Gestão" title="Equipa" />
      <div className="d-flex justify-content-between align-items-center mb-4 gap-3 flex-wrap">
        <div className="d-flex gap-2 flex-wrap">
          <CFormInput
            aria-label="Pesquisar equipa"
            value={search}
            placeholder="Pesquisar por nome ou email"
            onChange={(event) => setSearch(event.target.value)}
            style={{ minWidth: 260 }}
          />
          <CFormSelect
            aria-label="Filtrar equipa por estado"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            style={{ minWidth: 220 }}
            options={[
              { value: 'all', label: 'Todos os estados' },
              { value: 'active', label: 'Com acesso / ativo' },
              { value: 'pending_invite', label: 'Convite pendente' },
              { value: 'invite_expired', label: 'Convite expirado' },
              { value: 'sync_error', label: 'Acesso por confirmar' },
              { value: 'blocked', label: 'Acesso bloqueado' },
              { value: 'archived', label: 'Arquivado' },
            ]}
          />
          <CFormSwitch id="members-include-archived" label="Mostrar arquivados" checked={includeArchived} onChange={(event) => setIncludeArchived(event.target.checked)} />
        </div>
        {canCreate && <div className="d-flex gap-2">
          <CButton component="a" href="/imports?resource=teachers" color="secondary" variant="outline">Importar CSV</CButton>
          <CButton color="primary" onClick={() => openModal()} className="d-flex align-items-center gap-2" data-tutorial-target="new-member"><CIcon icon={cilPlus} />Adicionar membro</CButton>
        </div>}
      </div>
      {isError && (
        <div className="mb-3">
          <FeedbackBanner
            tone="danger"
            action={<CButton color="link" className="p-0" onClick={() => refetch()}>Tentar novamente</CButton>}
          >
            {getApiErrorMessage(error, 'Não foi possível carregar a equipa.', 'team.load')}
          </FeedbackBanner>
        </div>
      )}
      {actionError && <div className="mb-3"><FeedbackBanner tone="danger">{actionError}</FeedbackBanner></div>}
      {showAvailability && !isLoading && !isError && !availabilityTeacher && (
        <div className="mb-3"><FeedbackBanner tone="warning"
          action={<CButton color="link" className="p-0" onClick={closeAvailability}>Fechar</CButton>}>
          Professor não encontrado. Abra a disponibilidade através da equipa.
        </FeedbackBanner></div>
      )}
      {canCreate && <BulkRemovalActions bulk={bulk} message="Os membros com histórico serão arquivados; os restantes poderão ser removidos definitivamente. O acesso será removido." />}
      <div className="table-responsive">
        <table className="table align-middle">
          <thead><tr>{canCreate && <th className="selection-column"><BulkSelectionCheckbox label="Selecionar todos os membros disponíveis" checked={removableMembers.length > 0 && bulk.available.length === removableMembers.length} mixed={bulk.available.length > 0 && bulk.available.length < removableMembers.length} onChange={bulk.toggleAll} disabled={!removableMembers.length || bulk.pending} /></th>}<th>Nome</th><th>Email</th><th>Tipo</th><th>Estado</th><th>Competências</th><th className="text-end">Ações</th></tr></thead>
          <tbody>
            {isLoading && <tr><td colSpan={canCreate ? 7 : 6}><CSpinner size="sm" /> A carregar equipa...</td></tr>}
            {!isLoading && members.map((member) => {
              const [accessLabel, accessColor] = accessLabels[member.access_status] ?? [member.access_status, 'secondary']
              const [lifecycleLabel, lifecycleColor] = lifecycleLabels[member.lifecycle_status] ?? [member.lifecycle_status, 'secondary']
              const providerUnconfirmed = member.provider_state === 'unconfirmed'
              const accessErrorMessage = member.access_error_category
                ? accessErrorMessages[member.access_error_category] || accessErrorMessages.unknown
                : null
              return (
                <tr key={member.id} className={bulk.selected.includes(member.id) ? 'bulk-selected' : undefined}>
                  {canCreate && <td className="selection-column"><BulkSelectionCheckbox label={`Selecionar ${member.organization_display_name}`} checked={bulk.selected.includes(member.id)} onChange={() => bulk.toggle(member.id)} disabled={!member.actions?.can_remove || bulk.pending} /></td>}
                  <td className="fw-semibold">{member.organization_display_name}</td>
                  <td>{member.email}</td>
                  <td>
                    {member.capabilities.includes('teacher') && <CBadge color="primary" className="me-1">Professor</CBadge>}
                    {member.capabilities.includes('admin') && <CBadge color="dark">Administrador</CBadge>}
                    {member.capabilities.includes('teacher') && member.teacher_presence?.lunch_required === false && (
                      <CBadge color="secondary" className="ms-1">Sem almoço</CBadge>
                    )}
                    {member.capabilities.includes('teacher') && member.teacher_presence?.minimum_hours != null && (
                      <CBadge color="secondary" className="ms-1">
                        {`Mín. ${member.teacher_presence.minimum_hours}h · furo ${member.teacher_presence.max_gap_hours}h`}
                      </CBadge>
                    )}
                  </td>
                  <td>
                    <CBadge color={lifecycleColor} className="me-1">{lifecycleLabel}</CBadge>
                    <CBadge color={accessColor}>{accessLabel}</CBadge>
                    {providerUnconfirmed && <CBadge color="warning" className="ms-1">Estado de acesso por confirmar</CBadge>}
                    {accessErrorMessage && <div className="text-danger small mt-1">{accessErrorMessage}</div>}
                    {member.support_reference && <div className="text-muted small mt-1">Referência para apoio: <code>{member.support_reference}</code></div>}
                    {member.access_status === 'pending_invite' && (
                      <div className="text-muted small mt-1">Convite enviado; aguarda aceitação.</div>
                    )}
                  </td>
                  <td className="small text-muted">
                    {member.capabilities.includes('teacher')
                      ? member.subject_ids?.length === 1
                        ? '1 selecionada'
                        : member.subject_ids?.length
                          ? `${member.subject_ids.length} selecionadas`
                          : 'Sem competências'
                      : '-'}
                  </td>
                  <td className="text-end">
                    <CButton color="primary" variant="ghost" size="sm" aria-label="Editar membro" disabled={!canUpdate} onClick={() => openModal(member)} data-tutorial-target={`edit-member-${member.id}`}><CIcon icon={cilPencil} /></CButton>
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
        pendingText="A remover…"
        isLoading={removeMember.isPending}
      />
      {availabilityTeacher && (
        <TeacherAvailabilityModal
          key={`${availabilityTeacher.id}:${searchParams.get('on_date') ?? ''}`}
          teacher={availabilityTeacher}
          onDate={searchParams.get('on_date') || undefined}
          onClose={closeAvailability}
        />
      )}
        <MemberModal
        key={`${modalVisible ? 'open' : 'closed'}-${selectedMember?.id ?? 'new'}`}
        visible={modalVisible && !showAvailability && !removeTarget}
        member={managedMember}
        subjects={subjects}
        onClose={() => setModalVisible(false)}
        onSave={save}
        isSaving={activeMutation.isPending || resendInvitation.isPending || retrySync.isPending || restoreMember.isPending}
        actionVersion={actionVersion}
        canEdit={!managedMember || Boolean(managedMember.actions?.can_edit)}
        actions={memberActions(managedMember)}
        onAvailability={canUpdate && !isTutorial && managedMember?.teacher_id && managedMember.lifecycle_status === 'active'
          ? () => setSearchParams({ teacher_id: String(managedMember.teacher_id), panel: 'availability' })
          : undefined}
          error={activeMutation.error || actionErrorSource}
          competenciesOnly={isTutorial}
      />
    </div>
  )
}

export default Members
