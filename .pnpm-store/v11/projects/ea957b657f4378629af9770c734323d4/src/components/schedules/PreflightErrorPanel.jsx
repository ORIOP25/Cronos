import PropTypes from 'prop-types'
import { CAlert } from '@coreui/react'

const PreflightErrorPanel = ({ problems }) => (
  <CAlert color="danger" className="mb-4">
    <strong>Não é possível gerar o horário — pré-validação falhou:</strong>
    <ul className="mb-0 mt-2">
      {problems.map(p => <li key={p}>{p}</li>)}
    </ul>
  </CAlert>
)

PreflightErrorPanel.propTypes = {
  problems: PropTypes.arrayOf(PropTypes.string).isRequired,
}

export default PreflightErrorPanel
