// Ficheiro: src/components/DefaultLayout.jsx
import React from 'react';
import { Outlet, Link, useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { auth } from '../apiClient';
import { useAuthStore } from '../store';

const DefaultLayout = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const logout = useAuthStore((state) => state.logout);
  const user = useAuthStore((state) => state.user); // Objeto completo { email, role... }

  const handleLogout = async () => {
    try {
      await auth.logout();
    } catch (e) {
      // Handled: Logout errors are safely ignored (e.g. cookie already expired)
      console.error('Logout error (safely ignored):', e);
    }
    queryClient.clear(); // Limpa cache de React Query para evitar data leak entre sessões
    logout();
    navigate('/login');
  };

  // Helper para mostrar nome bonito do cargo
  const getRoleLabel = () => {
    if (!user) return '';
    if (user.role === 'admin') return 'Diretor';
    if (user.role === 'teacher') return 'Professor';
    return user.role;
  };

  return (
    <div style={{ display: 'flex', minHeight: '100vh', fontFamily: "'Inter', 'Segoe UI', sans-serif" }}>
      {/* --- SIDEBAR --- */}
      <aside style={{
        width: '260px',
        background: 'linear-gradient(180deg, var(--rs-sidebar-start) 0%, var(--rs-sidebar-end) 100%)',
        color: 'var(--rs-sidebar-text)',
        padding: '24px 16px',
        display: 'flex',
        flexDirection: 'column',
        position: 'sticky',
        top: 0,
        height: '100vh',
        overflowY: 'auto',
        flexShrink: 0,
      }}>
        <h2 style={{ marginBottom: '32px', color: 'var(--rs-sidebar-brand)', fontSize: '1.4rem', fontWeight: '700', letterSpacing: '-0.5px' }}>
          Horário Zen
        </h2>
        
        <nav style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          
          {/* Menu para DIRETORES */}
          {user?.role === 'admin' && (
            <>
              <Link to="/dashboard" style={linkStyle}>Dashboard</Link>
              <Link to="/schedules" style={linkStyle}>Horários</Link>
              <Link to="/schedules/audit" style={linkStyle}>Auditoria Técnica</Link>
              <Link to="/absences" style={linkStyle}>Faltas</Link>
              
              {/* Separador de Secção */}
              <div style={sectionLabelStyle}>Pedagogia</div>
              <Link to="/courses" style={linkStyle}>Cursos</Link>
              <Link to="/teachers" style={linkStyle}>Professores</Link>
              <Link to="/subjects" style={linkStyle}>Disciplinas</Link>
              
              <div style={sectionLabelStyle}>Recursos</div>
              <Link to="/rooms" style={linkStyle}>Salas</Link>
              <Link to="/config" style={linkStyle}>Configuração</Link>
            </>
          )}

          {/* Menu para TODOS */}
          <Link to="/my-availability" style={linkStyle}>Minhas Preferências</Link>
        </nav>

        {/* Rodapé da Sidebar */}
        <div style={{ marginTop: 'auto', paddingTop: '20px', borderTop: '1px solid var(--rs-sidebar-divider)' }}>
          <div style={{ marginBottom: '16px' }}>
            <p style={{ fontSize: '0.85rem', color: 'var(--rs-sidebar-text)', fontWeight: '600', margin: 0 }}>
              {user ? user.email : 'Convidado'}
            </p>
            <span style={{ fontSize: '0.7rem', color: 'var(--rs-sidebar-section)', textTransform: 'uppercase', letterSpacing: '1px' }}>
              {getRoleLabel()}
            </span>
          </div>
          <button onClick={handleLogout} style={logoutButtonStyle}>Sair</button>
        </div>
      </aside>

      {/* --- MAIN CONTENT --- */}
      <main style={{ flex: 1, backgroundColor: 'var(--rs-body-bg)', padding: '32px', overflowY: 'auto' }}>
        <Outlet />
      </main>
    </div>
  );
};

// Estilos — Retro Sunset
const linkStyle = {
  color: 'var(--rs-sidebar-link)',
  textDecoration: 'none',
  padding: '10px 14px',
  borderRadius: '8px',
  display: 'block',
  fontSize: '0.9rem',
  fontWeight: '500',
  transition: 'all 0.2s ease',
};

const sectionLabelStyle = {
  fontSize: '0.65rem',
  color: 'var(--rs-sidebar-section)',
  textTransform: 'uppercase',
  letterSpacing: '1.5px',
  marginTop: '20px',
  marginBottom: '8px',
  fontWeight: '700',
  paddingLeft: '14px',
};

const logoutButtonStyle = {
  width: '100%',
  padding: '10px',
  backgroundColor: 'transparent',
  color: 'var(--rs-sidebar-logout)',
  border: '1px solid var(--rs-sidebar-logout-border)',
  borderRadius: '8px',
  cursor: 'pointer',
  fontWeight: '600',
  fontSize: '0.85rem',
  transition: 'all 0.2s ease',
};

export default DefaultLayout;