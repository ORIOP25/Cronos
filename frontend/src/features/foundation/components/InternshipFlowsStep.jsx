import { CButton, CCard, CCardBody, CCol, CFormInput, CFormLabel, CRow } from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilPlus, cilTrash } from '@coreui/icons'
import PortugueseDateInput from '../../../components/PortugueseDateInput'

export function InternshipFlowsStep({ values, fieldErrors = {}, onChange }) {
  const flows = Array.isArray(values.internship_flows) ? values.internship_flows : []

  const updateFlow = (index, patch) => {
    onChange(
      'internship_flows',
      flows.map((flow, position) => (position === index ? { ...flow, ...patch } : flow)),
    )
  }

  const addFlow = () => {
    onChange('internship_flows', [...flows, { name: '', start_date: '', end_date: '' }])
  }

  const removeFlow = (index) => {
    onChange('internship_flows', flows.filter((_, position) => position !== index))
  }

  return (
    <div className="foundation-step-internship">
      <h4 tabIndex="-1" className="h5 mb-3 text-dark fw-bold">9. Fluxos de Estágio (opcional)</h4>
      <p className="text-muted small mb-4">
        Registe os períodos em que as turmas estarão em estágio. Neste passo os fluxos ficam sem
        turmas; pode associar as turmas mais tarde, nas configurações da escola. Se não existirem
        estágios, avance sem adicionar fluxos.
      </p>

      {flows.map((flow, index) => (
        <CCard key={`internship-flow-${index}`} className="border-0 shadow-sm mb-3">
          <CCardBody>
            <CRow className="g-3 align-items-start">
              <CCol md={5}>
                <CFormLabel htmlFor={`internship-flow-name-${index}`}>Nome do fluxo</CFormLabel>
                <CFormInput
                  id={`internship-flow-name-${index}`}
                  value={flow.name || ''}
                  placeholder="Ex: Estágio do 10.º ano"
                  onChange={(event) => updateFlow(index, { name: event.target.value })}
                />
              </CCol>
              <CCol md={3}>
                <CFormLabel htmlFor={`internship-flow-start-${index}`}>Início</CFormLabel>
                <PortugueseDateInput
                  id={`internship-flow-start-${index}`}
                  value={flow.start_date || ''}
                  onChange={(value) => updateFlow(index, { start_date: value })}
                />
              </CCol>
              <CCol md={3}>
                <CFormLabel htmlFor={`internship-flow-end-${index}`}>Fim</CFormLabel>
                <PortugueseDateInput
                  id={`internship-flow-end-${index}`}
                  value={flow.end_date || ''}
                  onChange={(value) => updateFlow(index, { end_date: value })}
                />
              </CCol>
              <CCol md={1} className="d-flex align-items-end">
                <CButton
                  color="danger"
                  variant="ghost"
                  aria-label={`Remover fluxo ${index + 1}`}
                  onClick={() => removeFlow(index)}
                >
                  <CIcon icon={cilTrash} />
                </CButton>
              </CCol>
            </CRow>
          </CCardBody>
        </CCard>
      ))}

      {fieldErrors.internship_flows && (
        <div className="text-danger small mb-2" role="alert">{fieldErrors.internship_flows}</div>
      )}

      <CButton color="secondary" variant="outline" onClick={addFlow}>
        <CIcon icon={cilPlus} className="me-1" />
        Adicionar fluxo de estágio
      </CButton>
    </div>
  )
}
