import React, { useState, useEffect } from 'react'
import { Outlet, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { auth } from '../apiClient'
import { useAuthStore } from '../store'
import { ROUTE_MY_SCHEDULES } from '../roleAccess'
import { TXT } from '../utils/terminology'
import CIcon from '@coreui/icons-react'
import { 
  cilSpeedometer, cilCalendar, cilCheckCircle, cilPeople, 
  cilLibrary, cilEducation, cilRoom, cilSettings, cilUser,
  cilAccountLogout, cilHistory, cilMenu
} from '@coreui/icons'

const SIDEBAR_WIDTH = 280
const SIDEBAR_COLLAPSED_WIDTH = 72

const SidebarLink = ({ to, icon, children, collapsed }) => (
  <NavLink 
    to={to} 
    className={({ isActive }) => `zen-sidebar-item ${isActive ? 'active' : ''}`}
    style={({ isActive }) => ({
      color: isActive ? 'var(--rs-sidebar-brand)' : 'var(--rs-sidebar-link)',
      textDecoration: 'none',
      padding: collapsed ? '12px' : '12px 16px',
      borderRadius: '4px',
      display: 'flex',
      alignItems: 'center',
      gap: '12px',
      fontSize: '0.88rem',
      fontWeight: isActive ? '600' : '500',
      transition: 'all 0.3s cubic-bezier(0.2, 0.8, 0.2, 1)',
      backgroundColor: isActive ? 'rgba(255, 255, 255, 0.1)' : 'transparent',
      marginBottom: '2px',
      justifyContent: collapsed ? 'center' : 'flex-start',
      overflow: 'hidden',
      whiteSpace: 'nowrap',
    })}
    title={collapsed ? children : undefined}
  >
    <CIcon icon={icon} size="sm" style={{ opacity: 0.8, flexShrink: 0 }} />
    {!collapsed && children}
  </NavLink>
)

const DefaultLayout = () => {
  const location = useLocation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const logout = useAuthStore((state) => state.logout)
  const user = useAuthStore((state) => state.user)
  const isAdmin = user?.role === 'admin'
  const isTeacher = user?.role === 'teacher'
  const accessDeniedMessage = location?.state?.accessDeniedMessage ?? ''
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem('hz-sidebar-collapsed') === 'true'
    } catch {
      return false
    }
  })

  useEffect(() => {
    try {
      localStorage.setItem('hz-sidebar-collapsed', String(collapsed))
    } catch {
      // no-op
    }
  }, [collapsed])

  useEffect(() => {
    if (!accessDeniedMessage) return
    window.history.replaceState({}, document.title, `${location.pathname}${location.search}`)
  }, [accessDeniedMessage, location.pathname, location.search])

  const handleLogout = async () => {
    try {
      await auth.logout()
    } catch (e) {
      console.error('Logout error:', e)
    }
    queryClient.clear()
    logout()
    navigate('/login')
  }

  const getRoleLabel = () => {
    if (!user) return ''
    if (user.role === 'admin') return 'Diretor'
    if (user.role === 'teacher') return 'Professor'
    return user.role
  }

  const currentWidth = collapsed ? SIDEBAR_COLLAPSED_WIDTH : SIDEBAR_WIDTH

  return (
    <div style={{ display: 'flex', minHeight: '100vh', backgroundColor: 'var(--rs-body-bg)' }}>
      {/* --- SIDEBAR --- */}
      <aside style={{
        width: `${currentWidth}px`,
        backgroundColor: 'var(--brand-950)',
        color: 'var(--rs-sidebar-text)',
        padding: collapsed ? '24px 8px' : '32px 20px',
        display: 'flex',
        flexDirection: 'column',
        position: 'sticky',
        top: 0,
        height: '100vh',
        overflowY: 'auto',
        overflowX: 'hidden',
        flexShrink: 0,
        borderRight: '1px solid rgba(255, 255, 255, 0.03)',
        transition: 'width 0.3s cubic-bezier(0.2, 0.8, 0.2, 1), padding 0.3s ease',
        zIndex: 10,
      }}>
        {/* Toggle + Brand */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: collapsed ? 'center' : 'space-between',
          marginBottom: collapsed ? '32px' : '48px',
          paddingLeft: collapsed ? '0' : '8px',
        }}>
          {!collapsed && (
            <div>
              <h2 className="text-display" style={{ color: '#ffffff', fontSize: '1.6rem', margin: 0 }}>
                {TXT.SIDEBAR_BRAND} <span style={{ color: 'var(--rs-sidebar-brand)' }}>{TXT.SIDEBAR_BRAND_ACCENT}</span>
              </h2>
              <div className="luxury-line" style={{ width: '40px', margin: '12px 0' }} />
            </div>
          )}
          {collapsed && (
            <h2 className="text-display" style={{ color: '#ffffff', fontSize: '1.3rem', margin: 0 }}>
              HZ
            </h2>
          )}
          {!isAdmin && (
            <button
              type="button"
              onClick={() => setCollapsed(prev => !prev)}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--rs-sidebar-link)',
                cursor: 'pointer',
                padding: '4px',
                display: 'flex',
                alignItems: 'center',
                opacity: 0.6,
                transition: 'opacity 0.2s ease',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.opacity = '1' }}
              onMouseLeave={(e) => { e.currentTarget.style.opacity = '0.6' }}
              title={collapsed ? 'Expandir menu' : 'Colapsar menu'}
              aria-label={collapsed ? 'Expandir menu' : 'Colapsar menu'}
            >
              <CIcon icon={cilMenu} size="sm" />
            </button>
          )}
        </div>
        
        <nav style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          {isAdmin && (
            <>
              <SidebarLink to="/dashboard" icon={cilSpeedometer} collapsed={collapsed}>Dashboard</SidebarLink>
              <SidebarLink to="/schedules" icon={cilCalendar} collapsed={collapsed}>Horários</SidebarLink>
              <SidebarLink to="/schedules/audit" icon={cilHistory} collapsed={collapsed}>Auditoria</SidebarLink>
              <SidebarLink to="/absences" icon={cilCheckCircle} collapsed={collapsed}>Faltas</SidebarLink>
              <SidebarLink to="/timesheets" icon={cilCalendar} collapsed={collapsed}>Fecho Semanal</SidebarLink>
              
              {!collapsed && <div className="text-editorial" style={sectionLabelStyle}>Pedagogia</div>}
              <SidebarLink to="/courses" icon={cilEducation} collapsed={collapsed}>Cursos</SidebarLink>
              <SidebarLink to="/teachers" icon={cilPeople} collapsed={collapsed}>Professores</SidebarLink>
              <SidebarLink to="/subjects" icon={cilLibrary} collapsed={collapsed}>Disciplinas</SidebarLink>
              
              {!collapsed && <div className="text-editorial" style={sectionLabelStyle}>Recursos</div>}
              <SidebarLink to="/rooms" icon={cilRoom} collapsed={collapsed}>Salas</SidebarLink>
              <SidebarLink to="/config" icon={cilSettings} collapsed={collapsed}>Configuração</SidebarLink>
            </>
          )}

          {isTeacher && (
            <>
              <SidebarLink to="/my-availability" icon={cilUser} collapsed={collapsed}>Preferências</SidebarLink>
              <SidebarLink to={ROUTE_MY_SCHEDULES} icon={cilCalendar} collapsed={collapsed}>Meus Horários</SidebarLink>
            </>
          )}
        </nav>

        {/* Rodapé da Sidebar */}
        <div style={{ marginTop: 'auto', paddingTop: '24px', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
          {!collapsed && (
            <div style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '12px', 
              padding: '12px',
              backgroundColor: 'rgba(255,255,255,0.03)',
              borderRadius: '8px',
              marginBottom: '16px'
            }}>
              <div style={{ 
                width: '36px', 
                height: '36px', 
                borderRadius: '4px', 
                backgroundColor: 'var(--brand-800)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#ffffff',
                fontWeight: '700',
                flexShrink: 0,
              }}>
                {user?.email?.[0].toUpperCase()}
              </div>
              <div style={{ overflow: 'hidden' }}>
                <p style={{ fontSize: '0.85rem', color: 'var(--brand-50)', fontWeight: '600', margin: 0, textOverflow: 'ellipsis', whiteSpace: 'nowrap', overflow: 'hidden' }}>
                  {user ? user.email.split('@')[0] : 'Convidado'}
                </p>
                <span className="zen-caps" style={{ color: 'var(--rs-sidebar-section)', fontSize: '0.6rem' }}>
                  {getRoleLabel()}
                </span>
              </div>
            </div>
          )}
          {collapsed && (
            <div style={{
              display: 'flex',
              justifyContent: 'center',
              marginBottom: '16px',
            }}>
              <div style={{ 
                width: '36px', 
                height: '36px', 
                borderRadius: '4px', 
                backgroundColor: 'var(--brand-800)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#ffffff',
                fontWeight: '700',
              }}>
                {user?.email?.[0].toUpperCase()}
              </div>
            </div>
          )}
          <button 
            onClick={handleLogout} 
            className="btn-zen btn-zen-outline" 
            style={{ width: '100%', justifyContent: 'center', fontSize: '0.75rem', padding: '8px' }}
            type="button"
          >
            <CIcon icon={cilAccountLogout} size="sm" />
            {!collapsed && ' Sair'}
          </button>
        </div>
      </aside>

      {/* --- MAIN CONTENT --- */}
      <main style={{
        flex: 1,
        padding: isTeacher ? '24px 16px' : '48px',
        overflowY: 'auto',
        maxWidth: isTeacher ? '100%' : '1400px',
        margin: '0 auto',
        width: '100%',
      }}>
        {accessDeniedMessage && (
          <div role="alert" className="zen-toast zen-toast-warning" style={{ position: 'relative', marginBottom: '32px', animation: 'none' }}>
             {accessDeniedMessage}
          </div>
        )}
        <Outlet />
      </main>
    </div>
  )
}

const sectionLabelStyle = {
  fontSize: '0.7rem',
  color: 'var(--rs-sidebar-section)',
  letterSpacing: '0.1em',
  marginTop: '24px',
  marginBottom: '8px',
  paddingLeft: '16px',
}

export default DefaultLayout
