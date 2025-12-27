// Ficheiro: src/components/ProtectedRoute.jsx

import React from 'react'
import { Navigate } from 'react-router-dom'
import { useAuthStore } from '../store' // A nossa "caixa-forte"

const ProtectedRoute = ({ children }) => {
  // 1. Lê o token diretamente do store
  const accessToken = useAuthStore((state) => state.accessToken)

  // 2. A Lógica do "Guarda-Costas"
  if (!accessToken) {
    // Se NÃO houver token, redireciona para /login
    return <Navigate to="/login" replace />
  }

  // 3. Se houver token, deixa a "criança" (a página) ser renderizada
  return children
}

export default ProtectedRoute