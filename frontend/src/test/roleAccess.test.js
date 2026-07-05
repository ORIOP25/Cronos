// Testes para o sistema de role-based access (roleAccess.js).

import { describe, it, expect } from 'vitest'
import {
  ROUTE_DASHBOARD,
  ROUTE_CREATE_ORG,
  ROUTE_MY_AVAILABILITY,
  getDefaultRouteForMember,
  getForbiddenRedirectRoute,
} from '../roleAccess'

describe('roleAccess', () => {
  describe('getDefaultRouteForMember', () => {
    it('admin vai para dashboard', () => {
      expect(getDefaultRouteForMember({ default_mode: 'admin' })).toBe(ROUTE_DASHBOARD)
    })

    it('teacher vai para my-availability', () => {
      expect(getDefaultRouteForMember({ default_mode: 'teacher' })).toBe(ROUTE_MY_AVAILABILITY)
    })

    it('modo desconhecido redireciona para create-org', () => {
      expect(getDefaultRouteForMember({ default_mode: 'student' })).toBe(ROUTE_CREATE_ORG)
    })

    it('null/undefined redireciona para create-org', () => {
      expect(getDefaultRouteForMember(null)).toBe(ROUTE_CREATE_ORG)
      expect(getDefaultRouteForMember(undefined)).toBe(ROUTE_CREATE_ORG)
    })
  })

  describe('getForbiddenRedirectRoute', () => {
    it('admin redirecionado para dashboard', () => {
      expect(getForbiddenRedirectRoute({ default_mode: 'admin' })).toBe(ROUTE_DASHBOARD)
    })

    it('teacher redirecionado para my-availability', () => {
      expect(getForbiddenRedirectRoute({ default_mode: 'teacher' })).toBe(ROUTE_MY_AVAILABILITY)
    })
  })


})
