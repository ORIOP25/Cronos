import React from 'react'
import { Outlet, Link } from 'react-router-dom'
import { useAuthStore } from '../store'

import {
  CContainer, CSidebar, CSidebarBrand, CSidebarNav, CHeader, CHeaderBrand, CHeaderNav,
  CNavLink, CNavItem, CDropdown, CDropdownToggle, CDropdownMenu, CDropdownItem, CDropdownDivider, CAvatar
} from '@coreui/react'

import CIcon from '@coreui/icons-react'
import { cilSpeedometer, cilUser, cilAccountLogout, cilSettings } from '@coreui/icons'

const DefaultLayout = () => {
  const { userRole, userEmail, logout } = useAuthStore()

  return (
    // Usamos 'd-flex' para garantir que a Sidebar e o Conteúdo ficam lado a lado
    <div className="d-flex min-vh-100 bg-light">
      
      {/* 1. SIDEBAR (Estilo Dark Moderno) */}
      {/* Removemos 'sidebar-fixed' para evitar o erro de sobreposição */}
      <CSidebar 
        className="border-end d-flex flex-column" 
        colorScheme="dark" // <--- MUDANÇA: Tema Escuro Profissional
        style={{ width: '260px', flexShrink: 0 }} // Largura fixa
      >
        <CSidebarBrand className="d-none d-md-flex align-items-center justify-content-center py-3">
          <h5 className="m-0 fw-bold text-white tracking-wider">HORÁRIO-ZEN</h5>
        </CSidebarBrand>
        
        <CSidebarNav className="mt-2">
          <CNavItem>
            <CNavLink as={Link} to="/dashboard" className="py-3">
              <CIcon icon={cilSpeedometer} className="me-3" />
              Dashboard
            </CNavLink>
          </CNavItem>

          {userRole === 'admin' && (
            <CNavItem>
              <CNavLink as={Link} to="/import" className="py-3">
                <CIcon icon={cilSettings} className="me-3" />
                Gestão de Dados
              </CNavLink>
            </CNavItem>
          )}

          {userRole === 'teacher' && (
            <CNavItem>
              <CNavLink as={Link} to="/my-availability" className="py-3">
                <CIcon icon={cilUser} className="me-3" />
                Minha Disponibilidade
              </CNavLink>
            </CNavItem>
          )}
        </CSidebarNav>
      </CSidebar>

      {/* 2. CONTEÚDO PRINCIPAL */}
      <div className="d-flex flex-column flex-grow-1" style={{ minWidth: 0 }}>
        
        {/* HEADER (Branco e Limpo) */}
        <CHeader className="mb-4 bg-white border-bottom shadow-sm px-4" style={{ height: '70px' }}>
          <CContainer fluid className="d-flex align-items-center h-100 px-0">
            <CHeaderBrand className="fw-semibold text-secondary">
              {/* Breadcrumb simples ou Título */}
              Gestão Escolar
            </CHeaderBrand>
            
            <CHeaderNav className="ms-auto">
              <CDropdown variant="nav-item">
                <CDropdownToggle placement="bottom-end" className="py-0 d-flex align-items-center gap-3" caret={false}>
                  <div className="text-end d-none d-md-block">
                      <div className="fw-bold text-dark" style={{fontSize: '0.9rem'}}>
                        {userRole === 'admin' ? 'Direção' : 'Docente'}
                      </div>
                      <div className="text-muted small">{userEmail}</div>
                  </div>
                  <CAvatar color="primary" size="md" textColor="white" className="fw-bold shadow-sm">
                      {userEmail ? userEmail[0].toUpperCase() : 'U'}
                  </CAvatar>
                </CDropdownToggle>
                <CDropdownMenu className="pt-0 shadow border-0 mt-2" placement="bottom-end">
                  <div className="bg-light p-2 border-bottom mb-2 text-center small text-muted">
                    Conta: {userRole}
                  </div>
                  <CDropdownItem href="#" className="py-2">
                    <CIcon icon={cilUser} className="me-2" /> Perfil
                  </CDropdownItem>
                  <CDropdownDivider />
                  <CDropdownItem onClick={logout} style={{cursor: 'pointer'}} className="py-2 text-danger">
                    <CIcon icon={cilAccountLogout} className="me-2" /> Sair
                  </CDropdownItem>
                </CDropdownMenu>
              </CDropdown>
            </CHeaderNav>
          </CContainer>
        </CHeader>

        {/* ÁREA DE CONTEÚDO (Com padding e scroll) */}
        <div className="flex-grow-1 px-4 pb-5" style={{ overflowY: 'auto' }}>
          <Outlet />
        </div>
        
        <footer className="mt-auto bg-white py-3 text-center text-muted small border-top">
            Horário-Zen v0.3 &copy; 2025
        </footer>
      </div>
    </div>
  )
}

export default DefaultLayout