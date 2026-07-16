import { describe, it, expect } from 'vitest'
import {
  ROUTE_CREATE_ORG,
  canAccessTeacherRoutes,
  getDefaultRouteForMember,
  hasMemberCapability,
  isActiveMember,
} from '../roleAccess'

describe('roleAccess', () => {
  describe('getDefaultRouteForMember', () => {
    it('admin vai para dashboard', () => {
      expect(getDefaultRouteForMember({ default_mode: 'admin' })).toBe('/dashboard')
    })

    it('teacher vai para my-availability', () => {
      expect(getDefaultRouteForMember({ default_mode: 'teacher' })).toBe('/my-availability')
    })

    it('modo desconhecido redireciona para create-org', () => {
      expect(getDefaultRouteForMember({ default_mode: 'student' })).toBe(ROUTE_CREATE_ORG)
    })

    it('null/undefined redireciona para create-org', () => {
      expect(getDefaultRouteForMember(null)).toBe(ROUTE_CREATE_ORG)
      expect(getDefaultRouteForMember(undefined)).toBe(ROUTE_CREATE_ORG)
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
