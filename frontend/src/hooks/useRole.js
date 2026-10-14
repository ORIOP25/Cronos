import { useCurrentMember } from '../features/members/data'
import { canAccessTeacherRoutes, hasMemberCapability } from '../roleAccess'

export function useRole() {
  const { data: member, isLoading, isError } = useCurrentMember()
  return {
    member,
    isLoading,
    isError,
    isAdmin: hasMemberCapability(member, 'admin'),
    isTeacher: canAccessTeacherRoutes(member),
  }
}
