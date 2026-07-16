import { useCurrentMember } from '../features/members/data'

export function useRole() {
  const { data: member, isLoading, isError } = useCurrentMember()
  const capabilities = new Set(member?.capabilities ?? [])
  const hasActiveAccess = member?.access_status === 'active' && member?.lifecycle_status === 'active'
  return {
    member,
    isLoading,
    isError,
    isAdmin: hasActiveAccess && capabilities.has('admin'),
    isTeacher: hasActiveAccess && capabilities.has('teacher') && Boolean(member?.teacher_id),
  }
}
