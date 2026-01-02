import React from 'react';
import { Outlet, Link, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store'; // Import corrigido com chavetas

const DefaultLayout = () => {
  const navigate = useNavigate();
  const logout = useAuthStore((state) => state.logout);
  const userEmail = useAuthStore((state) => state.user);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div style={{ display: 'flex', minHeight: '100vh', fontFamily: 'Arial, sans-serif' }}>
      {/* --- MENU LATERAL --- */}
      <aside style={{ width: '250px', backgroundColor: '#1e293b', color: 'white', padding: '20px', display: 'flex', flexDirection: 'column' }}>
        <h2 style={{ marginBottom: '30px', color: '#60a5fa', fontSize: '1.5rem' }}>Horário-Zen 🧘</h2>
        
        <nav style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <Link to="/dashboard" style={linkStyle}>📊 Dashboard</Link>
          <Link to="/teachers" style={linkStyle}>👨‍🏫 Professores</Link>
          <Link to="/my-availability" style={linkStyle}>📅 Minhas Preferências</Link>
        </nav>

        <div style={{ marginTop: 'auto', paddingTop: '20px', borderTop: '1px solid #334155' }}>
          <p style={{ fontSize: '0.8rem', color: '#94a3b8', marginBottom: '10px' }}>
            User: {userEmail || 'Convidado'}
          </p>
          <button onClick={handleLogout} style={logoutButtonStyle}>Sair</button>
        </div>
      </aside>

      {/* --- CONTEÚDO PRINCIPAL --- */}
      <main style={{ flex: 1, backgroundColor: '#f1f5f9', padding: '30px', overflowY: 'auto' }}>
        <Outlet />
      </main>
    </div>
  );
};

// Estilos
const linkStyle = {
  color: '#e2e8f0',
  textDecoration: 'none',
  padding: '12px',
  borderRadius: '6px',
  backgroundColor: 'rgba(255,255,255,0.05)',
  display: 'block',
  transition: 'all 0.2s',
};

const logoutButtonStyle = {
  width: '100%',
  background: 'transparent',
  border: '1px solid #ef4444',
  color: '#ef4444',
  padding: '8px',
  borderRadius: '4px',
  cursor: 'pointer',
  fontWeight: 'bold'
};

export default DefaultLayout;