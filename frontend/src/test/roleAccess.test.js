// Testes para o sistema de role-based access (roleAccess.js).

import { describe, it, expect } from 'vitest'
import {
  USER_ROLE_ADMIN,
  USER_ROLE_TEACHER,
  ROUTE_LOGIN,
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

    it('role desconhecido redireciona para login', () => {
      expect(getDefaultRouteForRole('student')).toBe(ROUTE_LOGIN)
    })

    it('null/undefined redireciona para login', () => {
      expect(getDefaultRouteForRole(null)).toBe(ROUTE_LOGIN)
      expect(getDefaultRouteForRole(undefined)).toBe(ROUTE_LOGIN)
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

  describe('Clerk role-based access (T26-T28)', () => {
    it('org:admin tem acesso a /dashboard, /teachers (T26)', () => {
      const { ROLE_ALLOWED_APP_ROUTES } = require('../roleAccess')
      expect(ROLE_ALLOWED_APP_ROUTES['org:admin']).toContain('/dashboard')
      expect(ROLE_ALLOWED_APP_ROUTES['org:admin']).toContain('/teachers')
    })

    it('org:member tem acesso a /my-availability, /my-schedules (T27)', () => {
      const { ROLE_ALLOWED_APP_ROUTES } = require('../roleAccess')
      expect(ROLE_ALLOWED_APP_ROUTES['org:member']).toContain('/my-availability')
      expect(ROLE_ALLOWED_APP_ROUTES['org:member']).toContain('/my-schedules')
    })

    it('org:member NÃO tem acesso a /dashboard (T28)', () => {
      const { ROLE_ALLOWED_APP_ROUTES } = require('../roleAccess')
      expect(ROLE_ALLOWED_APP_ROUTES['org:member']).not.toContain('/dashboard')
      expect(ROLE_ALLOWED_APP_ROUTES['org:member']).not.toContain('/config')
    })
  })
})
