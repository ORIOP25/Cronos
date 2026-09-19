import { cilCheckCircle } from '@coreui/icons'
import CIconModule from '@coreui/icons-react'

const CIcon = CIconModule.CIcon ?? CIconModule.default ?? CIconModule

export default function ContactSuccess({ name, onReset }) {
  return (
    <div className="cronos-questionnaire__success">
      <CIcon icon={cilCheckCircle} size="xl" />
      <h2>Pedido recebido{name ? `, ${name}` : ''}</h2>
      <p>A equipa do Cronos entrará em contacto para combinar a demonstração.</p>
      <button type="button" className="cronos-button cronos-button--secondary" onClick={onReset}>Voltar ao início</button>
    </div>
  )
}
