export const ROUTE_DASHBOARD = '/dashboard'
export const ROUTE_MY_AVAILABILITY = '/my-availability'
export const ROUTE_MY_SCHEDULES = '/my-schedules'
export const ROUTE_CREATE_ORG = '/create-org'

const MODE_DEFAULT_ROUTE = Object.freeze({
  admin: ROUTE_DASHBOARD,
  teacher: ROUTE_MY_AVAILABILITY,
})

export function getDefaultRouteForMember(member) {
  return MODE_DEFAULT_ROUTE[member?.default_mode] ?? ROUTE_CREATE_ORG
}

export function getForbiddenRedirectRoute(member) {
  return getDefaultRouteForMember(member)
}
