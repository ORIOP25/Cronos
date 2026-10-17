export const ROUTE_DASHBOARD = '/dashboard'
export const ROUTE_MY_AVAILABILITY = '/my-availability'
export const ROUTE_MY_SCHEDULES = '/my-schedules'
export const ROUTE_FOUNDATION = '/foundation'
export const ROUTE_FOUNDATION_WAITING = '/foundation/waiting'
export const ROUTE_SCHOOL_CONFIG = '/config'

const MODE_DEFAULT_ROUTE = Object.freeze({
  admin: ROUTE_DASHBOARD,
  teacher: ROUTE_MY_AVAILABILITY,
})

export function getDefaultRouteForMember(member) {
  return MODE_DEFAULT_ROUTE[member?.default_mode] ?? ROUTE_DASHBOARD
}

export function isFoundationComplete(member) {
  return member?.foundation_status === 'COMPLETED'
}

// Only the organization founder owns the Foundation wizard, and only while
// still an active administrator. Every other member waits until the founder
// completes it. Completed organizations never use these routes; callers
// resolve the role default first.
export function getFoundationLandingRoute(member) {
  const canRunWizard =
    hasMemberCapability(member, 'admin') && member?.can_manage_foundation === true
  return canRunWizard ? ROUTE_FOUNDATION : ROUTE_FOUNDATION_WAITING
}

export function getMemberRoute(member) {
  return isFoundationComplete(member)
    ? getDefaultRouteForMember(member)
    : getFoundationLandingRoute(member)
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
