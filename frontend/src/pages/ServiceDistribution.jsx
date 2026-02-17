/**
 * @deprecated Este ficheiro está obsoleto.
 * A funcionalidade de atribuição de professores foi movida para ClassSubjects.jsx
 * Navegar para: /courses/:courseId/classes/:classId/subjects
 * 
 * TODO: Apagar este ficheiro
 */

import React from 'react'
import { Navigate } from 'react-router-dom'

const ServiceDistribution = () => {
  // Redirecionar para a página de cursos
  return <Navigate to="/courses" replace />
}

export default ServiceDistribution
