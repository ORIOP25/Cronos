import { CAlert } from '@coreui/react'

const PreflightErrorPanel = ({ problems }) => (
  <CAlert color="danger" className="mb-4">
    <strong>Não é possível gerar o horário — pré-validação falhou:</strong>
    <ul className="mb-0 mt-2">
      {problems.map(p => <li key={p}>{p}</li>)}
    </ul>
  </CAlert>
)

export default PreflightErrorPanel
