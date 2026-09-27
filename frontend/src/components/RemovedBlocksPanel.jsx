import {
  CCard,
  CCardBody,
  CCardHeader,
  CTable,
  CTableBody,
  CTableDataCell,
  CTableHead,
  CTableHeaderCell,
  CTableRow,
} from '@coreui/react'
import { formatDate } from '../utils/formatUtils'

const shortTime = (value) => (value ? String(value).slice(0, 5) : '—')

const OCCURRENCE_LABELS = {
  GIVEN: 'Dada',
  GAP: 'Falta registada',
  SUBSTITUTED: 'Substituída',
}

const LOG_LABELS = {
  PENDING: 'Pendente',
  OCCURRENCE: 'Ocorrência registada',
  COMPLETED: 'Concluída',
}

function recordLabel(block) {
  if (block.occurrence_status) {
    return OCCURRENCE_LABELS[block.occurrence_status] ?? block.occurrence_status
  }
  if (block.lesson_log_status) {
    return LOG_LABELS[block.lesson_log_status] ?? block.lesson_log_status
  }
  return 'Sem registo'
}

export default function RemovedBlocksPanel({ blocks = [] }) {
  return (
    <CCard className="border-0 shadow-sm mt-4">
      <CCardHeader className="bg-transparent fw-semibold">Histórico de aulas retiradas</CCardHeader>
      <CCardBody className="p-0">
        {blocks.length === 0 ? (
          <p className="text-muted small m-3 mb-3">
            Sem aulas retiradas nesta semana. Ao guardar um fluxo de estágio, as aulas afetadas
            aparecem aqui para consulta.
          </p>
        ) : (
          <CTable small responsive className="mb-0">
            <CTableHead>
              <CTableRow>
                <CTableHeaderCell>Data</CTableHeaderCell>
                <CTableHeaderCell>Início</CTableHeaderCell>
                <CTableHeaderCell>Disciplina</CTableHeaderCell>
                <CTableHeaderCell>Professor</CTableHeaderCell>
                <CTableHeaderCell>Estado</CTableHeaderCell>
                <CTableHeaderCell>Registo preservado</CTableHeaderCell>
              </CTableRow>
            </CTableHead>
            <CTableBody>
              {blocks.map((block) => (
                <CTableRow key={block.id}>
                  <CTableDataCell className="text-nowrap">{formatDate(block.date)}</CTableDataCell>
                  <CTableDataCell>{shortTime(block.start_time)}</CTableDataCell>
                  <CTableDataCell>{block.subject_name ?? `Disciplina ${block.subject_id}`}</CTableDataCell>
                  <CTableDataCell>{block.teacher_name ?? `Professor ${block.teacher_id}`}</CTableDataCell>
                  <CTableDataCell>{block.status === 'CANCELED' ? 'Cancelada' : 'Retirada'}</CTableDataCell>
                  <CTableDataCell>
                    <span className="d-block">{recordLabel(block)}</span>
                    {block.lesson_log_summary && (
                      <span className="text-muted small d-block">{block.lesson_log_summary}</span>
                    )}
                  </CTableDataCell>
                </CTableRow>
              ))}
            </CTableBody>
          </CTable>
        )}
      </CCardBody>
    </CCard>
  )
}
