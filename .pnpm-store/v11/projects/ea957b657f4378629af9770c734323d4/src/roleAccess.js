export const USER_ROLE_ADMIN = 'org:admin'
export const USER_ROLE_TEACHER = 'org:member'

export const ROUTE_LOGIN = '/login'
export const ROUTE_DASHBOARD = '/dashboard'
export const ROUTE_MY_AVAILABILITY = '/my-availability'
export const ROUTE_MY_SCHEDULES = '/my-schedules'
export const ROUTE_MY_PROGRESS = '/my-progress'

export const ROLE_DEFAULT_ROUTE = Object.freeze({
  [USER_ROLE_ADMIN]: ROUTE_DASHBOARD,
  [USER_ROLE_TEACHER]: ROUTE_MY_AVAILABILITY,
})



export function getDefaultRouteForRole(role) {
  return ROLE_DEFAULT_ROUTE[role] ?? '/create-org'
}

export function getForbiddenRedirectRoute(role) {
  return ROLE_DEFAULT_ROUTE[role] ?? ROUTE_LOGIN
}
