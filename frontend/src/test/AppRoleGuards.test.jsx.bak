import React from 'react'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen } from '@testing-library/react'
import App from '../App'
import { renderWithProviders } from './testUtils'
import { useAuthStore } from '../store'

vi.mock('../pages/Login', () => ({ default: () => <div>LOGIN_PAGE</div> }))
vi.mock('../pages/Register', () => ({ default: () => <div>REGISTER_PAGE</div> }))
vi.mock('../pages/Dashboard', () => ({ default: () => <div>DASHBOARD_PAGE</div> }))
vi.mock('../pages/MyAvailability', () => ({ default: () => <div>MY_AVAIL_PAGE</div> }))
vi.mock('../pages/MySchedules', () => ({ default: () => <div>MY_SCHEDULES_PAGE</div> }))
vi.mock('../pages/Teachers', () => ({ default: () => <div>TEACHERS_PAGE</div> }))
vi.mock('../pages/Rooms', () => ({ default: () => <div>ROOMS_PAGE</div> }))
vi.mock('../pages/Subjects', () => ({ default: () => <div>SUBJECTS_PAGE</div> }))
vi.mock('../pages/SchoolConfig', () => ({ default: () => <div>CONFIG_PAGE</div> }))
vi.mock('../pages/Schedules', () => ({ default: () => <div>SCHEDULES_PAGE</div> }))
vi.mock('../pages/Occurrences', () => ({ default: () => <div>OCCURRENCES_PAGE</div> }))
vi.mock('../pages/ScheduleAuditDashboard', () => ({ default: () => <div>AUDIT_PAGE</div> }))
vi.mock('../pages/Courses', () => ({ default: () => <div>COURSES_PAGE</div> }))
vi.mock('../pages/CourseDetails', () => ({ default: () => <div>COURSE_DETAILS_PAGE</div> }))
vi.mock('../pages/ClassDetails', () => ({ default: () => <div>CLASS_DETAILS_PAGE</div> }))
vi.mock('../pages/ClassSubjects', () => ({ default: () => <div>CLASS_SUBJECTS_PAGE</div> }))

function setAuthenticatedRole(role, teacherId = null) {
  useAuthStore.setState({
    isAuthenticated: true,
    user: {
      email: `${role}@test.pt`,
      role,
      teacherId,
      orgId: 1,
      orgName: 'Org Test',
    },
  })
}

describe('App role guards', () => {
  beforeEach(() => {
    useAuthStore.setState({
      isAuthenticated: false,
      user: null,
    })
    window.history.pushState({}, '', '/login')
  })

  it('professor em rota admin e redirecionado para my-availability', async () => {
    setAuthenticatedRole('teacher', 11)
    window.history.pushState({}, '', '/dashboard')

    renderWithProviders(<App />)

    expect(await screen.findByText('MY_AVAIL_PAGE')).toBeInTheDocument()
    expect(screen.getByText('Acesso bloqueado: esta área é exclusiva para admin.')).toBeInTheDocument()
    expect(screen.queryByText('DASHBOARD_PAGE')).not.toBeInTheDocument()
  })

  it('admin em rota professor e redirecionado para dashboard', async () => {
    setAuthenticatedRole('admin')
    window.history.pushState({}, '', '/my-availability')

    renderWithProviders(<App />)

    expect(await screen.findByText('DASHBOARD_PAGE')).toBeInTheDocument()
    expect(screen.queryByText('MY_AVAIL_PAGE')).not.toBeInTheDocument()
  })

  it('professor consegue aceder a my-schedules', async () => {
    setAuthenticatedRole('teacher', 22)
    window.history.pushState({}, '', '/my-schedules')

    renderWithProviders(<App />)

    expect(await screen.findByText('MY_SCHEDULES_PAGE')).toBeInTheDocument()
  })

  it('professor em /schedules e redirecionado para my-availability', async () => {
    setAuthenticatedRole('teacher', 22)
    window.history.pushState({}, '', '/schedules')

    renderWithProviders(<App />)

    expect(await screen.findByText('MY_AVAIL_PAGE')).toBeInTheDocument()
    expect(screen.queryByText('SCHEDULES_PAGE')).not.toBeInTheDocument()
  })

  it('role unknown no index autenticado redireciona para login', async () => {
    setAuthenticatedRole('unknown-role')
    window.history.pushState({}, '', '/')

    renderWithProviders(<App />)

    expect(await screen.findByText('LOGIN_PAGE')).toBeInTheDocument()
  })

  it('estado autenticado corrompido (user null) em rota teacher redireciona para login', async () => {
    useAuthStore.setState({
      isAuthenticated: true,
      user: null,
    })
    window.history.pushState({}, '', '/my-schedules')

    renderWithProviders(<App />)

    expect(await screen.findByText('LOGIN_PAGE')).toBeInTheDocument()
    expect(screen.queryByText('MY_SCHEDULES_PAGE')).not.toBeInTheDocument()
  })
})
