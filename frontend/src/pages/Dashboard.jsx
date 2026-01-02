import React, { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../apiClient'

// Componentes do Projeto
import AnalyticsHeatmap from '../components/AnalyticsHeatmap'
import ReplacementModal from '../components/ReplacementModal'

// CoreUI & Icons
import { 
  CButton, 
  CCard, 
  CCardBody, 
  CCardHeader, 
  CSpinner, 
  CAlert, 
  CContainer,
  CProgress
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilMediaPlay } from '@coreui/icons'

// FullCalendar
import FullCalendar from '@fullcalendar/react'
import timeGridPlugin from '@fullcalendar/timegrid'
import dayGridPlugin from '@fullcalendar/daygrid'
import interactionPlugin from '@fullcalendar/interaction'

const Dashboard = () => {
  const queryClient = useQueryClient()
  
  // --- Estados Locais ---
  const [selectedEvent, setSelectedEvent] = useState(null)
  const [generationStatus, setGenerationStatus] = useState('idle') // 'idle' | 'running' | 'success' | 'error'
  
  // --- 1. BUSCAR DADOS (Parallel Query) ---
  // Trazemos tudo de uma vez para garantir consistência no render
  const { data: fullData, isLoading, isError, error } = useQuery({
    queryKey: ['dashboardData'],
    queryFn: async () => {
      const [schedule, timeslots, rooms, lessons, subjects, classes, teachers] = await Promise.all([
        apiClient.get('/schedule/latest').then(r => r.data),
        apiClient.get('/import/timeslots').then(r => r.data),
        apiClient.get('/import/rooms').then(r => r.data),
        apiClient.get('/import/lessons').then(r => r.data),
        apiClient.get('/import/subjects').then(r => r.data),
        apiClient.get('/import/classes').then(r => r.data),
        apiClient.get('/import/teachers').then(r => r.data)
      ])
      return { schedule, timeslots, rooms, lessons, subjects, classes, teachers }
    },
    refetchOnWindowFocus: false, // Evita recarregar sempre que mudas de tab
    staleTime: 60000 // Cache de 1 minuto para não saturar o backend
  })

  // --- 2. GERAÇÃO DE HORÁRIO (Mutation & Polling) ---
  const generateMutation = useMutation({
    mutationFn: async () => {
      // [CORREÇÃO] Rota atualizada para o standard REST definido no backend
      const res = await apiClient.post('/schedule/generate') 
      return res.data
    },
    onSuccess: (data) => {
      setGenerationStatus('running')
      // Iniciamos o polling para saber quando termina
      pollStatus(data.task_id)
    },
    onError: (err) => {
      console.error("Falha ao iniciar geração:", err)
      setGenerationStatus('error')
    }
  })

  // Função recursiva para verificar o estado da tarefa no Celery
  const pollStatus = async (id) => {
    try {
      const res = await apiClient.get(`/schedule/status/${id}`)
      const { status, result } = res.data // status = Estado do Celery; result = Retorno do Python

      if (status === 'SUCCESS') {
        // O script terminou, mas temos de ver se correu bem lá dentro
        if (result && result.status === 'Success') {
            setGenerationStatus('success')
            queryClient.invalidateQueries(['dashboardData'])
            queryClient.invalidateQueries(['heatmap']) 
        } else {
            // O script terminou mas com erro (ex: Faltam dados, Impossível resolver)
            console.error("Erro de Negócio:", result)
            setGenerationStatus('error')
            // Opcional: Podes guardar a mensagem de erro num estado para mostrar no Alerta
            // setErrorMessage(result.message || "Erro desconhecido")
        }
      } else if (status === 'FAILURE' || status === 'REVOKED') {
        // O script crashou
        setGenerationStatus('error')
      } else {
        // Ainda a rodar...
        setTimeout(() => pollStatus(id), 2000)
      }
    } catch (err) {
      console.error("Erro no polling:", err)
      setGenerationStatus('error')
    }
  }

  // --- 3. PROCESSAMENTO DE EVENTOS (Otimizado) ---
  // Usamos useMemo para não recalcular isto a cada render, apenas quando os dados mudam
  const calendarEvents = useMemo(() => {
    if (!fullData || !fullData.schedule) return []

    const { schedule, lessons, rooms, subjects, classes, teachers, timeslots } = fullData

    return schedule.map(item => {
        const lesson = lessons.find(l => l.id === item.lesson_id)
        const room = rooms.find(r => r.id === item.room_id)
        const slot = timeslots.find(t => t.id === item.timeslot_id)
        
        if (!lesson || !slot) return null

        const subject = subjects.find(s => s.id === lesson.subject_id)
        const teacher = teachers.find(t => t.id === lesson.teacher_id)
        const klass = classes.find(c => c.id === lesson.class_id)

        return {
            id: item.id.toString(), // FullCalendar prefere strings nos IDs
            title: `${subject?.name || 'Aula'} (${klass?.name || ''})`,
            // Horas
            startTime: slot.start_time,
            endTime: slot.end_time,
            // Dias da Semana (FullCalendar: 0=Domingo, 1=Segunda)
            // A nossa BD: 0=Segunda. Logo somamos 1.
            daysOfWeek: [slot.day_of_week + 1], 
            
            // Dados Extra (Para o Modal e Tooltips)
            extendedProps: {
                teacherName: teacher?.name,
                roomName: room?.name,
                subjectName: subject?.name,
                className: klass?.name,
                lessonId: lesson.id,
                timeslotId: slot.id
            },
            // Estilo
            backgroundColor: '#3b82f6', 
            borderColor: '#2563eb'
        }
    }).filter(Boolean)
  }, [fullData])

  // Customização visual de cada bloco no calendário
  const renderEventContent = (eventInfo) => {
    const { teacherName, roomName, subjectName, className } = eventInfo.event.extendedProps
    return (
      <div className="p-1 lh-1" style={{fontSize: '0.8rem'}}>
        <div className="fw-bold text-truncate">{subjectName}</div>
        <div className="text-truncate">{className}</div>
        <div className="small opacity-75 text-truncate">{teacherName}</div>
        <div className="badge bg-light text-dark mt-1 text-truncate" style={{maxWidth: '100%'}}>
          {roomName}
        </div>
      </div>
    )
  }

  return (
    <CContainer fluid>
      <div className="d-flex justify-content-between align-items-center mb-4">
        <h2 className="mb-0 fw-bold text-dark">Painel de Controlo</h2>
        
        {/* Botão de Ação Principal */}
        <CButton 
            color="primary" 
            onClick={() => generateMutation.mutate()} 
            disabled={generationStatus === 'running'}
            className="d-flex align-items-center gap-2 px-4"
        >
            {generationStatus === 'running' ? <CSpinner size="sm"/> : <CIcon icon={cilMediaPlay} />}
            {generationStatus === 'running' ? 'A Otimizar...' : 'Gerar Horário'}
        </CButton>
      </div>

      {/* Área de Feedback de Estado */}
      {generationStatus === 'running' && (
        <CAlert color="info" className="border-0 shadow-sm">
            <h5 className="alert-heading h6 fw-bold">Otimização em curso...</h5>
            <p className="small mb-2">O algoritmo está a analisar restrições e preferências. Isto pode demorar até 1 minuto.</p>
            <CProgress animated value={100} height={4} color="info" />
        </CAlert>
      )}
      {generationStatus === 'success' && (
        <CAlert color="success" dismissible onClose={() => setGenerationStatus('idle')} className="border-0 shadow-sm">
            <strong>Sucesso!</strong> Um novo horário otimizado foi gerado e aplicado.
        </CAlert>
      )}
      {generationStatus === 'error' && (
        <CAlert color="danger" dismissible onClose={() => setGenerationStatus('idle')} className="border-0 shadow-sm">
            <strong>Ups!</strong> Não foi possível gerar o horário. <br/>
            <small>Verifique se criou <b>Aulas</b> e <b>Blocos Horários</b>, ou se as restrições não são impossíveis.</small>
        </CAlert>
      )}

      {/* 1. Raio-X de Disponibilidade */}
      <CCard className="mb-4 border-0 shadow-sm">
        <CCardHeader className="bg-white fw-bold py-3">Disponibilidade dos Professores</CCardHeader>
        <CCardBody>
            <AnalyticsHeatmap />
        </CCardBody>
      </CCard>

      {/* 2. Calendário Principal */}
      <CCard className="border-0 shadow-sm">
        <CCardHeader className="bg-white py-3 d-flex justify-content-between align-items-center">
            <span className="fw-bold">Horário Escolar</span>
            <span className="badge bg-secondary">Versão Oficial</span>
        </CCardHeader>
        <CCardBody className="p-0">
            {isLoading ? (
                <div className="text-center p-5">
                    <CSpinner color="primary"/>
                    <div className="mt-3 text-muted small">A carregar estrutura do horário...</div>
                </div>
            ) : isError ? (
                <div className="p-4 text-center text-danger">
                    Erro ao carregar dados: {error.message}
                </div>
            ) : (
                <div className="p-3">
                    <FullCalendar
                        plugins={[timeGridPlugin, dayGridPlugin, interactionPlugin]}
                        initialView="timeGridWeek"
                        headerToolbar={{
                            left: 'prev,next today',
                            center: 'title',
                            right: 'timeGridWeek'
                        }}
                        // Ajustes de Visualização
                        weekends={false}
                        slotMinTime="08:00:00"
                        slotMaxTime="19:00:00"
                        allDaySlot={false}
                        contentHeight="auto"
                        locale="pt"
                        // Dados e Eventos
                        events={calendarEvents}
                        eventContent={renderEventContent}
                        eventClick={(info) => setSelectedEvent(info.event)}
                        // UI
                        slotEventOverlap={false}
                    />
                </div>
            )}
        </CCardBody>
      </CCard>

      {/* Modal de Substituição */}
      {selectedEvent && (
        <ReplacementModal 
            visible={!!selectedEvent} 
            eventData={selectedEvent} 
            onClose={() => setSelectedEvent(null)} 
        />
      )}

    </CContainer>
  )
}

export default Dashboard