// Ficheiro: src/components/ProtectedRoute.jsx

import React from 'react'
import { Navigate } from 'react-router-dom'
import { useAuthStore } from '../store'
import PropTypes from 'prop-types'

const ProtectedRoute = ({ children }) => {
  // 1. Estado de autenticacao
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)

  // 2. A Lógica do "Guarda-Costas"
  if (!isAuthenticated) {
    // Se NÃO houver token, redireciona para /login
    return <Navigate to="/login" replace />
  }

  // 3. Se houver token, deixa a "criança" (a página) ser renderizada
  return children
}

export default ProtectedRoute

ProtectedRoute.propTypes = {
  children: PropTypes.node.isRequired,
}