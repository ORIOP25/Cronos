import { useEffect, useRef, useState } from 'react'
import { Outlet, NavLink, useLocation } from 'react-router-dom'
import { useUser, useClerk, OrganizationSwitcher } from '@clerk/react'
import { COffcanvas, COffcanvasBody } from '@coreui/react'
import { useRole } from '../hooks/useRole'
import { TXT } from '../utils/terminology'
import FeedbackBanner from './FeedbackBanner'
import CIcon from '@coreui/icons-react'
import { cilMenu, cilX } from '@coreui/icons'
import { ADMIN_NAVIGATION, SIGN_OUT_ICON, TEACHER_NAVIGATION } from './appNavigation'
import { publicAsset } from '../utils/publicAsset'

const SIDEBAR_STORAGE_KEY = 'hz-sidebar-collapsed'

function SidebarLink({ to, icon, children, collapsed, onNavigate, activePath, disabled }) {
  if (disabled) return (
    <button type="button" className={`app-sidebar__link${activePath === to ? ' active' : ''}`} disabled title={collapsed ? children : undefined}>
      <CIcon icon={icon} size="sm" aria-hidden="true" />
      {!collapsed && <span>{children}</span>}
    </button>
  )
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

function AppSidebarContent({ collapsed, isAdmin, isTeacher, user, roleLabel, onToggle, onNavigate, onProfile, onSignOut, mobile = false, activePath, navigationDisabled = false }) {
  return (
    <div className={`app-sidebar${collapsed ? ' is-collapsed' : ''}${mobile ? ' app-sidebar--mobile' : ''}`}>
      <div className="app-sidebar__top">
        <div className="app-sidebar__brand-row">
          <div className="app-sidebar__brand">
            <img src={publicAsset('/logo-white.png')} alt={collapsed ? 'Cronos' : 'Cronos — Logótipo'} />
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
        {(isAdmin ? ADMIN_NAVIGATION : isTeacher ? TEACHER_NAVIGATION : []).map((item, index) => item.section
          ? (!collapsed && <div key={`section-${item.section}-${index}`} className="app-sidebar__section">{item.section}</div>)
          : <SidebarLink key={item.path} to={item.path} icon={item.icon} collapsed={collapsed} onNavigate={onNavigate} activePath={activePath} disabled={navigationDisabled}>{item.label}</SidebarLink>)}
      </nav>

      <div className="app-sidebar__footer">
        <button type="button" onClick={onProfile} className="app-sidebar__profile" title="Gerir conta" disabled={navigationDisabled}>
          <span className="app-sidebar__avatar">{user?.primaryEmailAddress?.emailAddress?.[0]?.toUpperCase() || '?'}</span>
          <span className="app-sidebar__profile-copy">
            <strong>{user?.primaryEmailAddress?.emailAddress?.split('@')[0] || 'Convidado'}</strong>
            <span>{roleLabel}</span>
          </span>
        </button>
        <button type="button" onClick={onSignOut} title="Terminar sessão" className="app-sidebar__logout" disabled={navigationDisabled}>
          <CIcon icon={SIGN_OUT_ICON} size="sm" aria-hidden="true" />
          <span>Terminar sessão</span>
        </button>
      </div>
    </div>
  )
}

const DefaultLayout = ({ children, activePath, navigationDisabled = false, navigationRole, className = '' }) => {
  const location = useLocation()
  const { user } = useUser()
  const { openUserProfile, signOut } = useClerk()
  const currentRole = useRole()
  const isAdmin = navigationRole === 'admin' || currentRole.isAdmin
  const isTeacher = navigationRole === 'teacher' || (!navigationRole && currentRole.isTeacher)
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
    <div className={`app-shell${className ? ` ${className}` : ''}`}>
      <aside className="app-sidebar--desktop" aria-label="Navegação principal">
        <AppSidebarContent collapsed={collapsed} isAdmin={isAdmin} isTeacher={isTeacher} user={user} roleLabel={roleLabel} onToggle={() => setCollapsed((value) => !value)} onNavigate={() => {}} onProfile={openUserProfile} onSignOut={() => signOut()} activePath={activePath} navigationDisabled={navigationDisabled} />
      </aside>
      <header className="app-mobile-header">
        <div className="app-mobile-header__brand"><img src={publicAsset('/logo-white.png')} alt="Cronos" /> Cronos</div>
        <button ref={menuButtonRef} type="button" className="app-mobile-header__menu" onClick={() => setMobileOpen(true)} aria-label="Abrir menu de navegação" aria-expanded={mobileOpen}>
          <CIcon icon={cilMenu} size="lg" aria-hidden="true" />
        </button>
      </header>
      {mobileOpen && <COffcanvas className="app-drawer" placement="start" visible={mobileOpen} onHide={closeMobile} backdrop scroll={false} aria-labelledby="app-drawer-title">
        <COffcanvasBody className="p-0">
          <span id="app-drawer-title" className="visually-hidden">Menu de navegação</span>
          <AppSidebarContent collapsed={false} isAdmin={isAdmin} isTeacher={isTeacher} user={user} roleLabel={roleLabel} onToggle={() => {}} onNavigate={closeMobile} onProfile={() => { closeMobile(); openUserProfile() }} onSignOut={() => { closeMobile(); signOut() }} activePath={activePath} navigationDisabled={navigationDisabled} mobile />
        </COffcanvasBody>
      </COffcanvas>}
      <main className="app-main">
        {!navigationDisabled && <div className="app-main__org" role="group" aria-label="Selecionar escola">
          <OrganizationSwitcher hidePersonal afterCreateOrganizationUrl="/foundation" afterSelectOrganizationUrl="/" afterLeaveOrganizationUrl="/" />
        </div>}
        {accessDeniedMessage && <div className="app-main__access-message"><FeedbackBanner tone="warning">{accessDeniedMessage}</FeedbackBanner></div>}
        {children ?? <Outlet />}
      </main>
    </div>
  )
}

export default DefaultLayout
