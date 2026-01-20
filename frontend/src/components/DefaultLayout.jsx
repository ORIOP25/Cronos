// Ficheiro: src/components/DefaultLayout.jsx
import React from 'react';
import { Outlet, Link, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store';

const DefaultLayout = () => {
  const navigate = useNavigate();
  const logout = useAuthStore((state) => state.logout);
  const user = useAuthStore((state) => state.user); // Objeto completo { email, role... }

  const handleLogout = () => {
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
    <div style={{ display: 'flex', minHeight: '100vh', fontFamily: 'Arial, sans-serif' }}>
      {/* --- SIDEBAR --- */}
      <aside style={{ width: '250px', backgroundColor: '#1e293b', color: 'white', padding: '20px', display: 'flex', flexDirection: 'column' }}>
        <h2 style={{ marginBottom: '30px', color: '#60a5fa', fontSize: '1.5rem' }}>Horário-Zen 🧘</h2>
        
        <nav style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          
          {/* Menu para DIRETORES */}
          {user?.role === 'admin' && (
            <>
              <Link to="/dashboard" style={linkStyle}>📊 Dashboard</Link>
              <Link to="/schedules" style={linkStyle}>📅 Horários</Link>
              <div className="my-2 border-top border-secondary"></div> {/* Separador */}
              
              {/* Secção de Pedagogia */}
              <div style={{ fontSize: '0.75rem', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.5px', marginTop: '15px', marginBottom: '10px', fontWeight: 'bold' }}>
                📚 PEDAGOGIA
              </div>
              <Link to="/courses" style={linkStyle}>🎓 Cursos</Link>
              <Link to="/modules" style={linkStyle}>📋 Módulos</Link>
              <Link to="/teachers" style={linkStyle}>👨‍🏫 Professores</Link>
              <Link to="/subjects" style={linkStyle}>📖 Disciplinas</Link>
              <Link to="/service-distribution" style={linkStyle}>🔗 Distribuição de Serviço</Link>
              
              <div className="my-2 border-top border-secondary"></div> {/* Separador */}
              
              {/* Secção de Recursos */}
              <div style={{ fontSize: '0.75rem', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.5px', marginTop: '15px', marginBottom: '10px', fontWeight: 'bold' }}>
                🏫 RECURSOS
              </div>
              <Link to="/classes" style={linkStyle}>👥 Turmas</Link>
              <Link to="/rooms" style={linkStyle}>🏫 Salas</Link>
              <Link to="/config" style={linkStyle}>⚙️ Configuração</Link>
            </>
          )}

          {/* Menu para TODOS (Professores e Diretores têm preferências) */}
          <Link to="/my-availability" style={linkStyle}>📅 Minhas Preferências</Link>
        </nav>

        {/* Rodapé da Sidebar */}
        <div style={{ marginTop: 'auto', paddingTop: '20px', borderTop: '1px solid #334155' }}>
          <div style={{ marginBottom: '15px' }}>
            <p style={{ fontSize: '0.9rem', color: '#fff', fontWeight: 'bold', margin: 0 }}>
              {user ? user.email : 'Convidado'}
            </p>
            <span style={{ fontSize: '0.75rem', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              {getRoleLabel()}
            </span>
          </div>
          <button onClick={handleLogout} style={logoutButtonStyle}>Sair</button>
        </div>
      </aside>

      {/* --- MAIN CONTENT --- */}
      <main style={{ flex: 1, backgroundColor: '#f1f5f9', padding: '30px', overflowY: 'auto' }}>
        <Outlet />
      </main>
    </div>
  );
};

// Estilos (Mantidos simples como tinhas)
const linkStyle = {
  color: '#e2e8f0',
  textDecoration: 'none',
  padding: '10px',
  borderRadius: '5px',
  display: 'block',
  transition: 'background 0.2s',
};

const logoutButtonStyle = {
  width: '100%',
  padding: '10px',
  backgroundColor: '#ef4444',
  color: 'white',
  border: 'none',
  borderRadius: '5px',
  cursor: 'pointer',
  fontWeight: 'bold',
};

export default DefaultLayout;