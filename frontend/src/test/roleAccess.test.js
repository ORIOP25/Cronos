// @vitest-environment node
import { describe, it, expect } from 'vitest'
import {
  ROUTE_DASHBOARD,
  ROUTE_FOUNDATION,
  ROUTE_FOUNDATION_WAITING,
  canAccessTeacherRoutes,
  getDefaultRouteForMember,
  getFoundationLandingRoute,
  getMemberRoute,
  hasMemberCapability,
  isActiveMember,
  isFoundationComplete,
} from '../roleAccess'

describe('roleAccess', () => {
  describe('getDefaultRouteForMember', () => {
    it('admin vai para dashboard', () => {
      expect(getDefaultRouteForMember({ default_mode: 'admin' })).toBe('/dashboard')
    })

    it('teacher vai para my-availability', () => {
      expect(getDefaultRouteForMember({ default_mode: 'teacher' })).toBe('/my-availability')
    })

    it('modo desconhecido usa o destino operacional, nunca a fundação', () => {
      expect(getDefaultRouteForMember({ default_mode: 'student' })).toBe(ROUTE_DASHBOARD)
    })

    it('null/undefined não é enviado para a fundação', () => {
      expect(getDefaultRouteForMember(null)).toBe(ROUTE_DASHBOARD)
      expect(getDefaultRouteForMember(undefined)).toBe(ROUTE_DASHBOARD)
    })
  })

  describe('foundation landing route', () => {
    const activeAdmin = {
      access_status: 'active',
      lifecycle_status: 'active',
      capabilities: ['admin'],
    }

    it('só o founder de uma organização incompleta abre o wizard', () => {
      expect(
        getFoundationLandingRoute({
          ...activeAdmin,
          foundation_status: 'IN_PROGRESS',
          can_manage_foundation: true,
        }),
      ).toBe(ROUTE_FOUNDATION)
    })

    it('um founder despromovido a professor espera em vez do wizard', () => {
      expect(
        getFoundationLandingRoute({
          access_status: 'active',
          lifecycle_status: 'active',
          capabilities: ['teacher'],
          foundation_status: 'IN_PROGRESS',
          can_manage_foundation: true,
        }),
      ).toBe(ROUTE_FOUNDATION_WAITING)
    })

    it('um founder sem acesso ativo espera em vez do wizard', () => {
      expect(
        getFoundationLandingRoute({
          ...activeAdmin,
          access_status: 'inactive',
          foundation_status: 'IN_PROGRESS',
          can_manage_foundation: true,
        }),
      ).toBe(ROUTE_FOUNDATION_WAITING)
    })

    it('um membro sem permissão de founder espera', () => {
      expect(
        getFoundationLandingRoute({
          ...activeAdmin,
          foundation_status: 'IN_PROGRESS',
          can_manage_foundation: false,
        }),
      ).toBe(ROUTE_FOUNDATION_WAITING)
      expect(getFoundationLandingRoute({ foundation_status: 'NOT_STARTED' })).toBe(
        ROUTE_FOUNDATION_WAITING,
      )
    })

    it('reconhece a fundação concluída', () => {
      expect(isFoundationComplete({ foundation_status: 'COMPLETED' })).toBe(true)
      expect(isFoundationComplete({ foundation_status: 'IN_PROGRESS' })).toBe(false)
      expect(isFoundationComplete(null)).toBe(false)
    })

    it('resolve o destino completo para o default do papel', () => {
      const member = {
        foundation_status: 'COMPLETED',
        default_mode: 'admin',
        can_manage_foundation: true,
      }
      expect(getMemberRoute(member)).toBe(ROUTE_DASHBOARD)
    })

    it('resolve uma organização incompleta pelo founder', () => {
      expect(
        getMemberRoute({
          ...activeAdmin,
          foundation_status: 'IN_PROGRESS',
          default_mode: 'admin',
          can_manage_foundation: true,
        }),
      ).toBe(ROUTE_FOUNDATION)
      expect(
        getMemberRoute({
          ...activeAdmin,
          foundation_status: 'IN_PROGRESS',
          default_mode: 'admin',
          can_manage_foundation: false,
        }),
      ).toBe(ROUTE_FOUNDATION_WAITING)
    })

    it('um founder despromovido espera em vez de abrir o wizard', () => {
      expect(
        getMemberRoute({
          access_status: 'active',
          lifecycle_status: 'active',
          capabilities: ['teacher'],
          default_mode: 'teacher',
          foundation_status: 'IN_PROGRESS',
          can_manage_foundation: true,
        }),
      ).toBe(ROUTE_FOUNDATION_WAITING)
    })
  })

  it('requires both active access and lifecycle state', () => {
    expect(isActiveMember({ access_status: 'active', lifecycle_status: 'active' })).toBe(true)
    expect(isActiveMember({ access_status: 'inactive', lifecycle_status: 'active' })).toBe(false)
    expect(isActiveMember({ access_status: 'active', lifecycle_status: 'archived' })).toBe(false)
  })

  it('grants only capabilities on an active membership', () => {
    const activeAdmin = {
      access_status: 'active',
      lifecycle_status: 'active',
      capabilities: ['admin'],
    }
    expect(hasMemberCapability(activeAdmin, 'admin')).toBe(true)
    expect(hasMemberCapability(activeAdmin, 'teacher')).toBe(false)
    expect(hasMemberCapability({ ...activeAdmin, access_status: 'inactive' }, 'admin')).toBe(false)
  })

  it('requires a teacher capability and linked teacher ID for teacher routes', () => {
    const teacher = {
      access_status: 'active',
      lifecycle_status: 'active',
      capabilities: ['teacher'],
      teacher_id: 7,
    }
    expect(canAccessTeacherRoutes(teacher)).toBe(true)
    expect(canAccessTeacherRoutes({ ...teacher, teacher_id: null })).toBe(false)
    expect(canAccessTeacherRoutes({ ...teacher, capabilities: ['admin'] })).toBe(false)
  })
})
