import React from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../apiClient'
import PropTypes from 'prop-types'
import {
  CModal, CModalHeader, CModalTitle, CModalBody, CModalFooter,
  CButton, CListGroup, CListGroupItem, CBadge, CSpinner, CAlert
} from '@coreui/react'

// Função auxiliar para formatar datas (YYYY-MM-DD)
const formatDate = (dateObj) => {
  if (!dateObj) return null
  return new Date(dateObj).toISOString().split('T')[0]
}

const fetchSuggestions = async ({ queryKey }) => {
  const [_, params] = queryKey
  // Agora exigimos date_str também
  if (!params.timeslot_id || !params.date_str) return []
  
  // ATENÇÃO: Mudámos o endpoint para o novo que criaste
  const response = await apiClient.get('/substitutions/suggestions', {
    params: params
  })
  return response.data
}

const ReplacementModal = ({ visible, onClose, eventData }) => {
  const queryClient = useQueryClient()

  // 1. EXTRAIR DADOS (Incluindo a DATA do evento clicado)
  const safeEventData = eventData || { extendedProps: {} }
  const { extendedProps, start } = safeEventData // 'start' vem do FullCalendar
  
  // Converter a data do evento para String (YYYY-MM-DD)
  const dateStr = formatDate(start)

  // 2. USE QUERY (Buscar Sugestões)
  const { data: suggestions, isLoading, isError } = useQuery({
    queryKey: ['suggestions', {
      timeslot_id: extendedProps?.timeslot_id,
      original_teacher_id: extendedProps?.teacher_id,
      date_str: dateStr // <--- O novo parametro crítico
    }],
    queryFn: fetchSuggestions,
    // Só ativa se tivermos eventData, estiver visível E tivermos uma data válida
    enabled: !!eventData && visible && !!dateStr
  })

  // 3. USE MUTATION (Criar Substituição)
  const mutation = useMutation({
    mutationFn: async (newTeacherId) => {
      // Endpoint novo para criar a substituição
      await apiClient.post('/substitutions/', {
        lesson_id: extendedProps?.lesson_id,     // Backend precisa disto
        timeslot_id: extendedProps.timeslot_id,
        original_teacher_id: extendedProps.teacher_id,
        substitute_teacher_id: newTeacherId,
        date: dateStr, // <--- A data específica
        reason: "Substituição pontual via Dashboard"
      })
    },
    onSuccess: () => {
      alert("Substituição agendada com sucesso!")
      // Invalidar queries para atualizar o calendário visualmente
      queryClient.invalidateQueries({ queryKey: ['substitutions'] })
      onClose()
    },
    onError: (err) => {
      const msg = err.response?.data?.detail || "Erro ao trocar."
      alert(msg)
    }
  })

  if (!eventData) return null

  return (
    <CModal visible={visible} onClose={onClose} size="lg">
      <CModalHeader onClose={onClose}>
        <CModalTitle>Gerir Substituição - {dateStr}</CModalTitle>
      </CModalHeader>
      
      <CModalBody>
        <p className="mb-4">
          A procurar substituto para <strong>{extendedProps?.teacher_name}</strong><br/>
          Aula: <strong>{safeEventData.title}</strong><br/>
          Data: <CBadge color="info">{dateStr}</CBadge>
        </p>

        {isLoading && <div className="text-center"><CSpinner/> A analisar horários para dia {dateStr}...</div>}
        
        {isError && <CAlert color="danger">Erro ao buscar sugestões.</CAlert>}

        {suggestions?.length === 0 && (
          <CAlert color="warning">Nenhum professor disponível neste dia/hora.</CAlert>
        )}

        {suggestions?.length > 0 && (
          <>
            <h5>Sugestões para esta data:</h5>
            <CListGroup>
              {suggestions.map((prof) => (
                <CListGroupItem key={prof.teacher_id} className="d-flex justify-content-between align-items-center">
                  <div>
                    <strong>{prof.teacher_name}</strong>
                    <br/>
                    <small className="text-muted">{prof.reason}</small>
                  </div>
                  
                  <div className="d-flex align-items-center gap-2">
                    {prof.priority === 1 ? (
                      <CBadge color="success">Mesma Disciplina</CBadge>
                    ) : (
                      <CBadge color="warning" className="text-dark">Outra Área</CBadge>
                    )}
                    
                    <CButton
                        color="primary" 
                        size="sm" 
                        variant="outline"
                        disabled={mutation.isPending}
                        onClick={() => mutation.mutate(prof.teacher_id)}
                    >
                        {mutation.isPending ? <CSpinner size="sm"/> : "Selecionar"}
                    </CButton>
                  </div>
                </CListGroupItem>
              ))}
            </CListGroup>
          </>
        )}

      </CModalBody>
      <CModalFooter>
        <CButton color="secondary" onClick={onClose}>Cancelar</CButton>
      </CModalFooter>
    </CModal>
  )
}

export default ReplacementModal

ReplacementModal.propTypes = {
  visible: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  eventData: PropTypes.object,
}