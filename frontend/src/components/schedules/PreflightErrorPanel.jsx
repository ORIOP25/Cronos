import { CAlert, CBadge } from '@coreui/react'
import { Link } from 'react-router-dom'

const PreflightErrorPanel = ({ issues }) => (
  <CAlert color="danger" className="mb-4">
    <strong>Não é possível gerar o horário — pré-validação falhou:</strong>
    <ul className="mb-0 mt-2">
      {issues.map((issue) => (
        <li key={`${issue.code}-${issue.route}`}>
          <CBadge color={issue.severity === 'WARNING' ? 'warning' : 'danger'} className="me-2">
            {issue.severity}
          </CBadge>
          {issue.message}
          {issue.route && (
            <Link className="ms-2" to={issue.route}>
              Corrigir
            </Link>
          )}
        </li>
      ))}
    </ul>
  </CAlert>
)

export default PreflightErrorPanel
