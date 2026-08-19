import { useEffect, useRef, useState } from 'react'
import { Outlet, NavLink, useLocation } from 'react-router-dom'
import { useUser, useClerk } from '@clerk/react'
import { COffcanvas, COffcanvasBody } from '@coreui/react'
import { ROUTE_MY_SCHEDULES } from '../roleAccess'
import { useRole } from '../hooks/useRole'
import { TXT } from '../utils/terminology'
import FeedbackBanner from './FeedbackBanner'
import CIcon from '@coreui/icons-react'
import {
  cilSpeedometer, cilCalendar, cilCheckCircle, cilPeople,
  cilLibrary, cilEducation, cilRoom, cilSettings, cilUser,
  cilMenu, cilChartPie, cilAccountLogout, cilX,
} from '@coreui/icons'

const SIDEBAR_STORAGE_KEY = 'hz-sidebar-collapsed'

function SidebarLink({ to, icon, children, collapsed, onNavigate }) {
  return (
    <NavLink
      to={to}
      onClick={onNavigate}
      className={({ isActive }) => `app-sidebar__link${isActive ? ' active' : ''}`}
      title={collapsed ? children : undefined}
    >
      <CIcon icon={icon} size="sm" aria-hidden="true" />
      {!collapsed && <span>{children}</span>}
    </NavLink>
  )
}

function AppSidebarContent({ collapsed, isAdmin, isTeacher, user, roleLabel, onToggle, onNavigate, onProfile, onSignOut, mobile = false }) {
  return (
    <div className={`app-sidebar${collapsed ? ' is-collapsed' : ''}${mobile ? ' app-sidebar--mobile' : ''}`}>
      <div className="app-sidebar__top">
        <div className="app-sidebar__brand-row">
          <div className="app-sidebar__brand">
            <img src="/logo.png" alt={collapsed ? 'Cronos' : 'Cronos — Logótipo'} />
            {!collapsed && <span className="app-sidebar__brand-name">{TXT.SIDEBAR_BRAND}</span>}
          </div>
          {!mobile && (
            <button type="button" className="app-sidebar__toggle" onClick={onToggle} aria-label={collapsed ? 'Expandir menu' : 'Colapsar menu'} title={collapsed ? 'Expandir menu' : 'Colapsar menu'}>
              <CIcon icon={cilMenu} size="sm" aria-hidden="true" />
            </button>
          )}
          {mobile && (
            <button type="button" className="app-sidebar__toggle" onClick={onNavigate} aria-label="Fechar menu">
              <CIcon icon={cilX} size="sm" aria-hidden="true" />
            </button>
          )}
        </div>
      </div>

      <nav className="app-sidebar__nav" aria-label="Navegação da aplicação">
        {isAdmin && <>
          <SidebarLink to="/dashboard" icon={cilSpeedometer} collapsed={collapsed} onNavigate={onNavigate}>Dashboard</SidebarLink>
          <SidebarLink to="/schedules" icon={cilCalendar} collapsed={collapsed} onNavigate={onNavigate}>Horários</SidebarLink>
          <SidebarLink to="/absences" icon={cilCheckCircle} collapsed={collapsed} onNavigate={onNavigate}>Faltas</SidebarLink>
          <SidebarLink to="/timesheets" icon={cilCalendar} collapsed={collapsed} onNavigate={onNavigate}>Fecho Semanal</SidebarLink>
          {!collapsed && <div className="app-sidebar__section">Pedagogia</div>}
          <SidebarLink to="/courses" icon={cilEducation} collapsed={collapsed} onNavigate={onNavigate}>Cursos</SidebarLink>
          <SidebarLink to="/members" icon={cilPeople} collapsed={collapsed} onNavigate={onNavigate}>Equipa</SidebarLink>
          <SidebarLink to="/subjects" icon={cilLibrary} collapsed={collapsed} onNavigate={onNavigate}>Disciplinas</SidebarLink>
          {!collapsed && <div className="app-sidebar__section">Recursos</div>}
          <SidebarLink to="/rooms" icon={cilRoom} collapsed={collapsed} onNavigate={onNavigate}>Salas</SidebarLink>
          <SidebarLink to="/config" icon={cilSettings} collapsed={collapsed} onNavigate={onNavigate}>Configuração</SidebarLink>
        </>}
        {isTeacher && <>
          <SidebarLink to="/my-availability" icon={cilUser} collapsed={collapsed} onNavigate={onNavigate}>Preferências</SidebarLink>
          <SidebarLink to={ROUTE_MY_SCHEDULES} icon={cilCalendar} collapsed={collapsed} onNavigate={onNavigate}>Meus Horários</SidebarLink>
          <SidebarLink to="/my-progress" icon={cilChartPie} collapsed={collapsed} onNavigate={onNavigate}>Meu Progresso</SidebarLink>
        </>}
      </nav>

      <div className="app-sidebar__footer">
        <button type="button" onClick={onProfile} className="app-sidebar__profile" title="Gerir conta">
          <span className="app-sidebar__avatar">{user?.primaryEmailAddress?.emailAddress?.[0]?.toUpperCase() || '?'}</span>
          <span className="app-sidebar__profile-copy">
            <strong>{user?.primaryEmailAddress?.emailAddress?.split('@')[0] || 'Convidado'}</strong>
            <span>{roleLabel}</span>
          </span>
        </button>
        <button type="button" onClick={onSignOut} title="Terminar sessão" className="app-sidebar__logout">
          <CIcon icon={cilAccountLogout} size="sm" aria-hidden="true" />
          <span>Terminar sessão</span>
        </button>
      </div>
    </div>
  )
}

const DefaultLayout = () => {
  const location = useLocation()
  const { user } = useUser()
  const { openUserProfile, signOut } = useClerk()
  const { isAdmin, isTeacher } = useRole()
  const menuButtonRef = useRef(null)
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem(SIDEBAR_STORAGE_KEY) === 'true' } catch { return false }
  })
  const [mobileOpen, setMobileOpen] = useState(false)
  const accessDeniedMessage = location?.state?.accessDeniedMessage ?? ''
  const roleLabel = isAdmin ? 'Diretor' : isTeacher ? 'Professor' : ''

  useEffect(() => {
    try { localStorage.setItem(SIDEBAR_STORAGE_KEY, String(collapsed)) } catch { /* storage is optional */ }
  }, [collapsed])

  useEffect(() => {
    const closeTimer = window.setTimeout(() => setMobileOpen(false), 0)
    return () => window.clearTimeout(closeTimer)
  }, [location.pathname, location.search])

  useEffect(() => {
    document.body.classList.toggle('app-drawer-open', mobileOpen)
    return () => document.body.classList.remove('app-drawer-open')
  }, [mobileOpen])

  useEffect(() => {
    if (!mobileOpen) return undefined
    const handleKeyDown = (event) => { if (event.key === 'Escape') setMobileOpen(false) }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [mobileOpen])

  const closeMobile = () => {
    setMobileOpen(false)
    window.setTimeout(() => menuButtonRef.current?.focus(), 0)
  }

  return (
    <div className="app-shell">
      <aside className="app-sidebar--desktop" aria-label="Navegação principal">
        <AppSidebarContent collapsed={collapsed} isAdmin={isAdmin} isTeacher={isTeacher} user={user} roleLabel={roleLabel} onToggle={() => setCollapsed((value) => !value)} onNavigate={() => {}} onProfile={openUserProfile} onSignOut={() => signOut()} />
      </aside>
      <header className="app-mobile-header">
        <div className="app-mobile-header__brand"><img src="/logo.png" alt="Cronos" /> Cronos</div>
        <button ref={menuButtonRef} type="button" className="app-mobile-header__menu" onClick={() => setMobileOpen(true)} aria-label="Abrir menu de navegação" aria-expanded={mobileOpen}>
          <CIcon icon={cilMenu} size="lg" aria-hidden="true" />
        </button>
      </header>
      {mobileOpen && <COffcanvas className="app-drawer" placement="start" visible={mobileOpen} onHide={closeMobile} backdrop scroll={false} aria-labelledby="app-drawer-title">
        <COffcanvasBody className="p-0">
          <span id="app-drawer-title" className="visually-hidden">Menu de navegação</span>
          <AppSidebarContent collapsed={false} isAdmin={isAdmin} isTeacher={isTeacher} user={user} roleLabel={roleLabel} onToggle={() => {}} onNavigate={closeMobile} onProfile={() => { closeMobile(); openUserProfile() }} onSignOut={() => { closeMobile(); signOut() }} mobile />
        </COffcanvasBody>
      </COffcanvas>}
      <main className="app-main">
        {accessDeniedMessage && <div className="app-main__access-message"><FeedbackBanner tone="warning">{accessDeniedMessage}</FeedbackBanner></div>}
        <Outlet />
      </main>
    </div>
  )
}

export default DefaultLayout
