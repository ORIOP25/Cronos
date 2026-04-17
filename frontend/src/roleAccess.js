export const USER_ROLE_ADMIN = 'admin'
export const USER_ROLE_TEACHER = 'teacher'

export const ROUTE_LOGIN = '/login'
export const ROUTE_DASHBOARD = '/dashboard'
export const ROUTE_MY_AVAILABILITY = '/my-availability'
export const ROUTE_MY_SCHEDULES = '/my-schedules'

export const ROLE_DEFAULT_ROUTE = Object.freeze({
  [USER_ROLE_ADMIN]: ROUTE_DASHBOARD,
  [USER_ROLE_TEACHER]: ROUTE_MY_AVAILABILITY,
})

export const ROLE_ALLOWED_APP_ROUTES = Object.freeze({
  [USER_ROLE_ADMIN]: Object.freeze([
    ROUTE_DASHBOARD,
    '/schedules',
    '/schedules/audit',
    '/absences',
    '/courses',
    '/teachers',
    '/subjects',
    '/rooms',
    '/config',
  ]),
  [USER_ROLE_TEACHER]: Object.freeze([
    ROUTE_MY_AVAILABILITY,
    ROUTE_MY_SCHEDULES,
  ]),
})

export function getDefaultRouteForRole(role) {
  return ROLE_DEFAULT_ROUTE[role] ?? ROUTE_LOGIN
}

export function getForbiddenRedirectRoute(role) {
  return ROLE_DEFAULT_ROUTE[role] ?? ROUTE_LOGIN
}
