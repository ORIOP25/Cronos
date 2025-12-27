import React from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../apiClient'
import {
  CModal, CModalHeader, CModalTitle, CModalBody, CModalFooter,
  CButton, CListGroup, CListGroupItem, CBadge, CSpinner, CAlert
} from '@coreui/react'

const fetchSuggestions = async ({ queryKey }) => {
  const [_, params] = queryKey
  // Se faltarem dados, não faz pedido (segurança extra)
  if (!params.timeslot_id) return []
  
  const response = await apiClient.get('/suggestions/replacement', {
    params: params
  })
  return response.data
}

const ReplacementModal = ({ visible, onClose, eventData }) => {
  const queryClient = useQueryClient()

  // 1. EXTRAIR DADOS DE FORMA SEGURA
  // Se eventData for null, usamos um objeto vazio para não crashar
  const safeEventData = eventData || { extendedProps: {} }
  const { extendedProps } = safeEventData

  // 2. USE QUERY (Corre sempre, mas 'enabled' controla se faz o pedido)
  const { data: suggestions, isLoading, isError } = useQuery({
    queryKey: ['suggestions', {
      timeslot_id: extendedProps?.timeslot_id,      // Uso de ?.
      class_id: extendedProps?.class_id,            // Uso de ?.
      missing_teacher_id: extendedProps?.teacher_id // Uso de ?.
    }],
    queryFn: fetchSuggestions,
    enabled: !!eventData && visible // Só ativa se eventData existir E modal visível
  })

  // 3. USE MUTATION (Corre sempre)
  const mutation = useMutation({
    mutationFn: async (newTeacherId) => {
      await apiClient.post('/schedule/swap', {
        schedule_id: parseInt(eventData.id),
        new_teacher_id: newTeacherId,
        class_id: extendedProps.class_id
      })
    },
    onSuccess: () => {
      alert("Troca efetuada com sucesso!")
      queryClient.invalidateQueries({ queryKey: ['fullScheduleData'] })
      onClose()
    },
    onError: (err) => {
      alert(err.response?.data?.detail || "Erro ao trocar.")
    }
  })

  // 4. RETURN ANTECIPADO (Agora é seguro fazer isto aqui)
  if (!eventData) return null

  return (
    <CModal visible={visible} onClose={onClose} size="lg">
      <CModalHeader onClose={onClose}>
        <CModalTitle>Gerir Substituição</CModalTitle>
      </CModalHeader>
      
      <CModalBody>
        <p className="mb-4">
          A procurar substituto para <strong>{extendedProps.teacher_name}</strong><br/>
          Aula: <strong>{eventData.title}</strong>
        </p>

        {isLoading && <div className="text-center"><CSpinner/> A analisar horários...</div>}
        
        {isError && <CAlert color="danger">Erro ao buscar sugestões.</CAlert>}

        {suggestions && suggestions.length === 0 && (
          <CAlert color="warning">Nenhum professor disponível neste horário.</CAlert>
        )}

        {suggestions && suggestions.length > 0 && (
          <>
            <h5>Sugestões Encontradas:</h5>
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
                      <CBadge color="success">Ideal (Antecipação)</CBadge>
                    ) : (
                      <CBadge color="warning" className="text-dark">Vigilância</CBadge>
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