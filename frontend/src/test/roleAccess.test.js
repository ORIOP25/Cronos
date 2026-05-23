// Testes para o sistema de role-based access (roleAccess.js).

import { describe, it, expect } from 'vitest'
import {
  USER_ROLE_ADMIN,
  USER_ROLE_TEACHER,
  ROUTE_DASHBOARD,
  getDefaultRouteForRole,
  getForbiddenRedirectRoute,
} from '../roleAccess'

describe('roleAccess', () => {
  describe('getDefaultRouteForRole', () => {
    it('admin vai para dashboard', () => {
      expect(getDefaultRouteForRole(USER_ROLE_ADMIN)).toBe(ROUTE_DASHBOARD)
    })

    it('teacher vai para my-availability', () => {
      expect(getDefaultRouteForRole(USER_ROLE_TEACHER)).toBe('/my-availability')
    })

    it('role desconhecido redireciona para create-org', () => {
      expect(getDefaultRouteForRole('student')).toBe('/create-org')
    })

    it('null/undefined redireciona para create-org', () => {
      expect(getDefaultRouteForRole(null)).toBe('/create-org')
      expect(getDefaultRouteForRole(undefined)).toBe('/create-org')
    })
  })

  describe('getForbiddenRedirectRoute', () => {
    it('admin redirecionado para dashboard', () => {
      expect(getForbiddenRedirectRoute(USER_ROLE_ADMIN)).toBe(ROUTE_DASHBOARD)
    })

    it('teacher redirecionado para my-availability', () => {
      expect(getForbiddenRedirectRoute(USER_ROLE_TEACHER)).toBe('/my-availability')
    })
  })


})
