// Ficheiro: src/components/DefaultLayout.jsx
import React from 'react';
import { Outlet, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { auth } from '../apiClient';
import { useAuthStore } from '../store';
import { ROUTE_MY_SCHEDULES } from '../roleAccess';
import CIcon from '@coreui/icons-react';
import { 
  cilSpeedometer, cilCalendar, cilCheckCircle, cilPeople, 
  cilLibrary, cilEducation, cilRoom, cilSettings, cilUser,
  cilAccountLogout, cilHistory
} from '@coreui/icons';

const SidebarLink = ({ to, icon, children }) => (
  <NavLink 
    to={to} 
    className={({ isActive }) => `zen-sidebar-item ${isActive ? 'active' : ''}`}
    style={({ isActive }) => ({
      color: isActive ? 'var(--brand-500)' : 'var(--rs-sidebar-link)',
      textDecoration: 'none',
      padding: '12px 16px',
      borderRadius: '4px',
      display: 'flex',
      alignItems: 'center',
      gap: '12px',
      fontSize: '0.88rem',
      fontWeight: isActive ? '600' : '500',
      transition: 'all 0.3s cubic-bezier(0.2, 0.8, 0.2, 1)',
      backgroundColor: isActive ? 'rgba(214, 176, 112, 0.08)' : 'transparent',
      marginBottom: '2px',
    })}
  >
    <CIcon icon={icon} size="sm" style={{ opacity: 0.8 }} />
    {children}
  </NavLink>
);

const DefaultLayout = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const logout = useAuthStore((state) => state.logout);
  const user = useAuthStore((state) => state.user);
  const isAdmin = user?.role === 'admin';
  const isTeacher = user?.role === 'teacher';
  const accessDeniedMessage = location?.state?.accessDeniedMessage ?? '';

  React.useEffect(() => {
    if (!accessDeniedMessage) return;
    window.history.replaceState({}, document.title, `${location.pathname}${location.search}`);
  }, [accessDeniedMessage, location.pathname, location.search]);

  const handleLogout = async () => {
    try {
      await auth.logout();
    } catch (e) {
      console.error('Logout error:', e);
    }
    queryClient.clear();
    logout();
    navigate('/login');
  };

  const getRoleLabel = () => {
    if (!user) return '';
    if (user.role === 'admin') return 'Diretor';
    if (user.role === 'teacher') return 'Professor';
    return user.role;
  };

  return (
    <div style={{ display: 'flex', minHeight: '100vh', backgroundColor: 'var(--rs-body-bg)' }}>
      {/* --- SIDEBAR --- */}
      <aside style={{
        width: '280px',
        backgroundColor: 'var(--brand-950)',
        color: 'var(--rs-sidebar-text)',
        padding: '32px 20px',
        display: 'flex',
        flexDirection: 'column',
        position: 'sticky',
        top: 0,
        height: '100vh',
        overflowY: 'auto',
        flexShrink: 0,
        borderRight: '1px solid rgba(255, 255, 255, 0.03)',
      }}>
        <div style={{ marginBottom: '48px', paddingLeft: '8px' }}>
          <h2 className="text-display" style={{ color: 'var(--brand-50)', fontSize: '1.6rem', margin: 0 }}>
            Horário <span style={{ color: 'var(--brand-500)' }}>Zen</span>
          </h2>
          <div className="luxury-line" style={{ width: '40px', margin: '12px 0' }} />
        </div>
        
        <nav style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          {isAdmin && (
            <>
              <SidebarLink to="/dashboard" icon={cilSpeedometer}>Dashboard</SidebarLink>
              <SidebarLink to="/schedules" icon={cilCalendar}>Horários</SidebarLink>
              <SidebarLink to="/schedules/audit" icon={cilHistory}>Auditoria</SidebarLink>
              <SidebarLink to="/absences" icon={cilCheckCircle}>Faltas</SidebarLink>
              
              <div className="text-editorial" style={sectionLabelStyle}>Pedagogia</div>
              <SidebarLink to="/courses" icon={cilEducation}>Cursos</SidebarLink>
              <SidebarLink to="/teachers" icon={cilPeople}>Professores</SidebarLink>
              <SidebarLink to="/subjects" icon={cilLibrary}>Disciplinas</SidebarLink>
              
              <div className="text-editorial" style={sectionLabelStyle}>Recursos</div>
              <SidebarLink to="/rooms" icon={cilRoom}>Salas</SidebarLink>
              <SidebarLink to="/config" icon={cilSettings}>Configuração</SidebarLink>
            </>
          )}

          {isTeacher && (
            <>
              <SidebarLink to="/my-availability" icon={cilUser}>Preferências</SidebarLink>
              <SidebarLink to={ROUTE_MY_SCHEDULES} icon={cilCalendar}>Meus Horários</SidebarLink>
            </>
          )}
        </nav>

        {/* Rodapé da Sidebar */}
        <div style={{ marginTop: 'auto', paddingTop: '24px', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
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
              color: 'var(--brand-500)',
              fontWeight: '700'
            }}>
              {user?.email?.[0].toUpperCase()}
            </div>
            <div style={{ overflow: 'hidden' }}>
              <p style={{ fontSize: '0.85rem', color: 'var(--brand-50)', fontWeight: '600', margin: 0, textOverflow: 'ellipsis', whiteSpace: 'nowrap', overflow: 'hidden' }}>
                {user ? user.email.split('@')[0] : 'Convidado'}
              </p>
              <span className="zen-caps" style={{ color: 'var(--brand-600)', fontSize: '0.6rem' }}>
                {getRoleLabel()}
              </span>
            </div>
          </div>
          <button 
            onClick={handleLogout} 
            className="btn-zen btn-zen-outline" 
            style={{ width: '100%', justifyContent: 'center', fontSize: '0.75rem', padding: '8px' }}
          >
            <CIcon icon={cilAccountLogout} size="sm" />
            Sair
          </button>
        </div>
      </aside>

      {/* --- MAIN CONTENT --- */}
      <main style={{ flex: 1, padding: '48px', overflowY: 'auto', maxWidth: '1400px', margin: '0 auto', width: '100%' }}>
        {accessDeniedMessage && (
          <div role="alert" className="zen-toast zen-toast-warning" style={{ position: 'relative', marginBottom: '32px', animation: 'none' }}>
             {accessDeniedMessage}
          </div>
        )}
        <Outlet />
      </main>
    </div>
  );
};

const sectionLabelStyle = {
  fontSize: '0.7rem',
  color: 'var(--brand-600)',
  letterSpacing: '0.1em',
  marginTop: '24px',
  marginBottom: '8px',
  paddingLeft: '16px',
};

export default DefaultLayout;