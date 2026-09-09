const ROUTE_DASHBOARD = '/dashboard'
const ROUTE_MY_AVAILABILITY = '/my-availability'
export const ROUTE_MY_SCHEDULES = '/my-schedules'
export const ROUTE_FOUNDATION = '/foundation'

const MODE_DEFAULT_ROUTE = Object.freeze({
  admin: ROUTE_DASHBOARD,
  teacher: ROUTE_MY_AVAILABILITY,
})

export function getDefaultRouteForMember(member) {
  return MODE_DEFAULT_ROUTE[member?.default_mode] ?? ROUTE_FOUNDATION
}

export function isActiveMember(member) {
  return member?.access_status === 'active' && member?.lifecycle_status === 'active'
}

export function hasMemberCapability(member, capability) {
  return isActiveMember(member) && member.capabilities?.includes(capability) === true
}

export function canAccessTeacherRoutes(member) {
  return hasMemberCapability(member, 'teacher') && Boolean(member.teacher_id)
}
