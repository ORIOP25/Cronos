import {
  CModal,
  CModalHeader,
  CModalTitle,
  CModalBody,
  CModalFooter,
  CButton,
  CProgress,
  CProgressBar,
  CBadge,
  CRow,
  CCol,
  CCard,
  CCardBody,
  CCardHeader,
  CTable,
  CTableHead,
  CTableRow,
  CTableHeaderCell,
  CTableBody,
  CTableDataCell,
} from '@coreui/react'

export function TutorialModal({
  isOpen,
  currentStep,
  currentStepIndex,
  totalSteps,
  progressPercent,
  completed: _completed,
  simulationData,
  onNext,
  onPrev,
  onSkip,
  onSkipTutorial,
  onClose,
}) {
  const isFirst = currentStepIndex === 0
  const isLast = currentStepIndex === totalSteps - 1
  const step = currentStep || {}

  return (
    <CModal
      visible={isOpen}
      onClose={onClose}
      size="xl"
      alignment="center"
      backdrop="static"
      data-testid="tutorial-modal"
    >
      <CModalHeader closeButton>
        <div className="d-flex flex-column w-100 me-3">
          <div className="d-flex justify-content-between align-items-center mb-1">
            <CModalTitle className="h5 mb-0">
              Tutorial Interativo: Motor Cronos
            </CModalTitle>
            <div className="d-flex gap-2 align-items-center">
              <CBadge color={step.chapter === 1 ? 'primary' : 'success'}>
                Capítulo {step.chapter || 1}: {step.chapter === 1 ? 'Fundação & Bases' : 'Planeamento & Operação'}
              </CBadge>
              <span className="text-muted small" data-testid="tutorial-step-counter">
                Passo {currentStepIndex + 1} de {totalSteps}
              </span>
            </div>
          </div>
          <CProgress height={4} className="mt-1">
            <CProgressBar value={progressPercent} color="primary" />
          </CProgress>
        </div>
      </CModalHeader>

      <CModalBody className="p-4">
        <CRow className="g-4">
          {/* Coluna Esquerda: Instruções e Conceitos */}
          <CCol md={5} className="d-flex flex-column justify-content-between border-end pe-md-4">
            <div>
              <div className="mb-2">
                <span className="text-primary fw-semibold text-uppercase small tracking-wide">
                  {step.subtitle}
                </span>
                <h3 className="h4 text-dark mt-1 mb-2 fw-bold">
                  {step.title}
                </h3>
              </div>
              <p className="text-secondary lead fs-6 mb-4">
                {step.description}
              </p>

              <div className="p-3 bg-light rounded-3 border mb-3">
                <h6 className="fw-semibold mb-2 text-dark">Dica Pedagógica & Regulatória:</h6>
                <p className="small text-muted mb-0">
                  {step.chapter === 1 && 'Esta sequência é uma simulação local: nenhum dado da sua escola é alterado.'}
                  {step.chapter === 2 && 'A simulação preserva a dívida de horas e o histórico de reparação para mostrar o fluxo.'}
                </p>
              </div>
            </div>

            <div className="pt-3 d-flex justify-content-between align-items-center">
              {step.isSkippable && !isLast ? (
                <CButton
                  variant="ghost"
                  color="secondary"
                  size="sm"
                  onClick={onSkip}
                  data-testid="tutorial-skip-button"
                >
                  Saltar este passo
                </CButton>
              ) : (
                <span className="badge bg-light text-muted border">Passo Fundamental</span>
              )}
              <span className="text-muted small">
                Progresso: {progressPercent}%
              </span>
            </div>
          </CCol>

          {/* Coluna Direita: Simulação Visual Interativa */}
          <CCol md={7} className="ps-md-4">
            <CCard className="shadow-sm border-0 bg-light">
              <CCardHeader className="bg-white border-bottom py-2 d-flex justify-content-between align-items-center">
                <span className="fw-semibold small text-uppercase text-secondary">
                  Simulação do Ambiente Cronos
                </span>
                <CBadge color="info" shape="rounded-pill">Simulação</CBadge>
              </CCardHeader>
              <CCardBody className="p-3">
                {step.chapter === 1 && (
                  <div>
                    <h6 className="fw-semibold mb-2">Parâmetros das Bases Escolares</h6>
                    <div className="d-flex gap-3 mb-2">
                      <div className="p-2 border rounded bg-white flex-fill">
                        <span className="small text-muted d-block">Início do Ano:</span>
                        <strong>{simulationData.startDate}</strong>
                      </div>
                      <div className="p-2 border rounded bg-white flex-fill">
                        <span className="small text-muted d-block">Data-Limite Rígida:</span>
                        <strong>{simulationData.hardEndDate}</strong>
                      </div>
                    </div>
                    <ul className="list-group list-group-flush small bg-white rounded border mt-2">
                      <li className="list-group-item d-flex justify-content-between">
                        <span>Bloco Letivo:</span>
                        <strong>{simulationData.slotDuration} min</strong>
                      </li>
                      <li className="list-group-item d-flex justify-content-between">
                        <span>Janela de Almoço:</span>
                        <strong>{simulationData.lunchStart} - {simulationData.lunchEnd}</strong>
                      </li>
                    </ul>
                  </div>
                )}

                {step.chapter === 2 && (
                  <div>
                    <h6 className="fw-semibold mb-2 text-primary">Pré-visualização do Horário Gerado</h6>
                    <div className="table-responsive bg-white rounded border">
                      <CTable small hover className="mb-0 text-center font-monospace small">
                        <CTableHead>
                          <CTableRow>
                            <CTableHeaderCell>Dia</CTableHeaderCell>
                            <CTableHeaderCell>Horário</CTableHeaderCell>
                            <CTableHeaderCell>Disciplina</CTableHeaderCell>
                            <CTableHeaderCell>Espaço</CTableHeaderCell>
                          </CTableRow>
                        </CTableHead>
                        <CTableBody>
                          {simulationData.gridPreview.map((item) => (
                            <CTableRow key={`${item.day}-${item.time}-${item.subject}`}>
                              <CTableDataCell className="fw-bold">{item.day}</CTableDataCell>
                              <CTableDataCell>{item.time}</CTableDataCell>
                              <CTableDataCell className="text-primary">{item.subject}</CTableDataCell>
                              <CTableDataCell><CBadge color="secondary">{item.room}</CBadge></CTableDataCell>
                            </CTableRow>
                          ))}
                        </CTableBody>
                      </CTable>
                    </div>
                  </div>
                )}
              </CCardBody>
            </CCard>
          </CCol>
        </CRow>
      </CModalBody>

      <CModalFooter className="d-flex justify-content-between">
        <div className="d-flex gap-2">
          <CButton color="secondary" variant="outline" onClick={onClose} data-testid="tutorial-exit-button">
            Sair do Tutorial
          </CButton>
          <CButton color="warning" variant="outline" onClick={onSkipTutorial} data-testid="tutorial-skip-all-button">
            Saltar guia
          </CButton>
        </div>
        <div className="d-flex gap-2">
          <CButton
            color="secondary"
            onClick={onPrev}
            disabled={isFirst}
            data-testid="tutorial-prev-button"
          >
            ← Anterior
          </CButton>
          <CButton
            color="primary"
            onClick={onNext}
            data-testid="tutorial-next-button"
          >
            {isLast ? 'Concluir Tutorial ✓' : 'Seguinte →'}
          </CButton>
        </div>
      </CModalFooter>
    </CModal>
  )
}
