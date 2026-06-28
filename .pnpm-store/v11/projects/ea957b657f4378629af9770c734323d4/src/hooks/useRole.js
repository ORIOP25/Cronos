import { useOrganization } from '@clerk/react'
import { USER_ROLE_ADMIN, USER_ROLE_TEACHER } from '../roleAccess'

export function useRole() {
  const { membership } = useOrganization()
  return {
    isAdmin: membership?.role === USER_ROLE_ADMIN,
    isTeacher: membership?.role === USER_ROLE_TEACHER,
  }
}
