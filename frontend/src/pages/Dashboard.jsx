import React, { useState, useMemo } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../apiClient'

// --- NOVOS IMPORTS (Os Hooks que criámos) ---
import { 
  useTeachers, 
  useRooms, 
  useSubjects, 
  useClasses, 
  useLessons, 
  useTimeslots, 
  useSchedule, 
  useSubstitutions 
} from '../hooks/useSchoolData'

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

// --- FUNÇÃO AUXILIAR (Fora do Componente) ---
// Gera uma chave única para identificar um "Buraco" no horário (Dia + SlotID)
const getSlotKey = (dateStr, timeslotId) => {
  return `${dateStr}_${timeslotId}`
}

const Dashboard = () => {
  const queryClient = useQueryClient()
  
  // --- Estados Locais ---
  const [selectedEvent, setSelectedEvent] = useState(null)
  const [generationStatus, setGenerationStatus] = useState('idle') 

  // --- 1. BUSCAR DADOS (Hooks Individuais e Otimizados) ---
  const { data: teachers, isLoading: l1 } = useTeachers()
  const { data: rooms, isLoading: l2 } = useRooms()
  const { data: subjects, isLoading: l3 } = useSubjects()
  const { data: classes, isLoading: l4 } = useClasses()
  const { data: lessons, isLoading: l5 } = useLessons()
  const { data: timeslots, isLoading: l6 } = useTimeslots()
  
  // Dados Dinâmicos
  const { data: schedule, isLoading: l7, isError, error } = useSchedule()
  const { data: substitutions, isLoading: l8 } = useSubstitutions()

  // Loading Global
  const isLoading = l1 || l2 || l3 || l4 || l5 || l6 || l7 || l8

  // --- 2. GERAÇÃO DE HORÁRIO ---
  const generateMutation = useMutation({
    mutationFn: async () => {
      const res = await apiClient.post('/schedule/generate') 
      return res.data
    },
    onSuccess: (data) => {
      setGenerationStatus('running')
      pollStatus(data.task_id)
    },
    onError: (err) => {
      console.error("Falha ao iniciar geração:", err)
      setGenerationStatus('error')
    }
  })

  const pollStatus = async (id) => {
    try {
      const res = await apiClient.get(`/schedule/status/${id}`)
      const { status, result } = res.data 

      if (status === 'SUCCESS') {
        if (result?.status === 'Success') {
            setGenerationStatus('success')
            queryClient.invalidateQueries({ queryKey: ['schedule'] })
            queryClient.invalidateQueries({ queryKey: ['heatmap'] }) 
        } else {
            console.error("Erro de Negócio:", result)
            setGenerationStatus('error')
        }
      } else if (status === 'FAILURE' || status === 'REVOKED') {
        setGenerationStatus('error')
      } else {
        setTimeout(() => pollStatus(id), 2000)
      }
    } catch (err) {
      console.error("Erro no polling:", err)
      setGenerationStatus('error')
    }
  }

  // --- 3. LÓGICA DE VISUALIZAÇÃO INTELIGENTE ---
  
  // A. Mapa de Bloqueios:
  // Cria um "Set" com todos os slots que têm substituição.
  // Permite verificar instantaneamente se uma aula deve ser escondida.
  const blockedSlots = useMemo(() => {
    const blocked = new Set()
    if (substitutions) {
        substitutions.forEach(sub => {
            // sub.date vem da BD como "YYYY-MM-DD"
            const key = getSlotKey(sub.date, sub.timeslot_id)
            blocked.add(key)
        })
    }
    return blocked
  }, [substitutions])

  // B. Processamento de Eventos:
  const calendarEvents = useMemo(() => {
    if (!schedule || !lessons || !rooms || !subjects || !classes || !teachers || !timeslots) return []

    // 1. Criar eventos "Normais" (Recorrentes)
    const regularEvents = schedule.map(item => {
        const lesson = lessons.find(l => l.id === item.lesson_id)
        const room = rooms.find(r => r.id === item.room_id)
        const slot = timeslots.find(t => t.id === item.timeslot_id)
        
        if (!lesson || !slot) return null

        const subject = subjects.find(s => s.id === lesson.subject_id)
        const teacher = teachers.find(t => t.id === lesson.teacher_id)
        const klass = classes.find(c => c.id === lesson.class_id)

        return {
            id: `regular-${item.id}`,
            title: `${subject?.name || 'Aula'} (${klass?.name || ''})`,
            startTime: slot.start_time,
            endTime: slot.end_time,
            daysOfWeek: [slot.day_of_week + 1],
            
            extendedProps: {
                lesson_id: lesson.id,
                timeslot_id: slot.id,
                teacher_id: teacher?.id,
                class_id: klass?.id,
                teacherName: teacher?.name,
                roomName: room?.name,
                subjectName: subject?.name,
                className: klass?.name,
                isSubstitution: false,
                type: 'regular' // FLAG IMPORTANTE: Identifica aula padrão
            },
            backgroundColor: 'var(--rs-event-bg)', 
            borderColor: 'var(--rs-event-border)'
        }
    }).filter(Boolean)

    // 2. Criar eventos de "Substituição" (Pontuais)
    const subEvents = (substitutions || []).map(sub => {
        const slot = timeslots.find(t => t.id === sub.timeslot_id)
        if (!slot) return null
        
        const newTeacher = teachers.find(t => t.id === sub.substitute_teacher_id)
        const lesson = lessons.find(l => l.id === sub.lesson_id)
        const subject = subjects.find(s => s.id === lesson?.subject_id)
        const klass = classes.find(c => c.id === lesson?.class_id)
        
        // Construção da data completa para posicionar no calendário
        const startDateTime = `${sub.date}T${slot.start_time}`
        const endDateTime = `${sub.date}T${slot.end_time}`

        return {
            id: `sub-${sub.id}`,
            title: `SUB: ${newTeacher?.name || 'Substituto'}`, 
            start: startDateTime,
            end: endDateTime,
            
            extendedProps: {
                lesson_id: sub.lesson_id,
                timeslot_id: sub.timeslot_id,
                teacher_id: newTeacher?.id,
                class_id: klass?.id,
                teacherName: newTeacher?.name,
                subjectName: subject?.name,
                className: klass?.name,
                isSubstitution: true,
                type: 'substitution' // FLAG IMPORTANTE: Identifica substituição
            },
            backgroundColor: 'var(--rs-sub-event-bg)', 
            borderColor: 'var(--rs-sub-event-border)'
        }
    }).filter(Boolean)

    return [...regularEvents, ...subEvents]

  }, [schedule, lessons, rooms, subjects, classes, teachers, timeslots, substitutions])

  // C. ClassNames Dinâmicos (Ocultação Visual):
  // O FullCalendar chama isto para cada bloco que vai desenhar no ecrã.
  const getEventClassNames = (arg) => {
    const { type, timeslot_id } = arg.event.extendedProps
    
    // Se for uma aula "Regular", perguntamos: "Há uma substituição aqui hoje?"
    if (type === 'regular') {
        // Obtemos a data onde este bloco específico está a ser desenhado (ex: 2026-03-12)
        const dateStr = arg.event.start.toISOString().split('T')[0]
        const key = getSlotKey(dateStr, timeslot_id)

        // Se a chave existir no bloqueio, aplicamos a classe 'd-none' (esconder)
        if (blockedSlots.has(key)) {
            return ['d-none'] 
        }
    }
    return []
  }

  // --- RENDERIZAÇÃO DO CONTEÚDO ---
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

  const renderCalendarContent = () => {
    if (isLoading) return <div className="text-center p-5"><CSpinner color="primary"/></div>
    if (isError) return <div className="p-4 text-center text-danger">Erro: {error?.message || "Erro desconhecido"}</div>
    return (
      <div className="p-3">
        <FullCalendar
          plugins={[timeGridPlugin, dayGridPlugin, interactionPlugin]}
          initialView="timeGridWeek"
          headerToolbar={{
            left: 'prev,next today',
            center: 'title',
            right: 'timeGridWeek'
          }}
          weekends={false}
          slotMinTime="08:00:00"
          slotMaxTime="19:00:00"
          allDaySlot={false}
          contentHeight="auto"
          locale="pt"
          events={calendarEvents}
          eventClassNames={getEventClassNames}
          eventContent={renderEventContent}
          eventClick={(info) => setSelectedEvent(info.event)}
          slotEventOverlap={false}
        />
      </div>
    )
  }

  return (
    <CContainer fluid>
      <div className="d-flex justify-content-between align-items-center mb-4">
        <h2 className="mb-0 fw-bold text-dark">Painel de Controlo</h2>
        
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

      {generationStatus === 'running' && (
        <CAlert color="info" className="border-0 shadow-sm">
            <h5 className="alert-heading h6 fw-bold">Otimização em curso...</h5>
            <p className="small mb-2">O algoritmo está a analisar restrições e preferências.</p>
            <CProgress animated value={100} height={4} color="info" />
        </CAlert>
      )}
      {generationStatus === 'success' && (
        <CAlert color="success" dismissible onClose={() => setGenerationStatus('idle')} className="border-0 shadow-sm">
            <strong>Sucesso!</strong> Horário gerado.
        </CAlert>
      )}
      {generationStatus === 'error' && (
        <CAlert color="danger" dismissible onClose={() => setGenerationStatus('idle')} className="border-0 shadow-sm">
            <strong>Erro!</strong> Verifique os dados.
        </CAlert>
      )}

      <CCard className="mb-4 border-0 shadow-sm">
        <CCardHeader className="bg-white fw-bold py-3">Disponibilidade dos Professores</CCardHeader>
        <CCardBody>
            <AnalyticsHeatmap />
        </CCardBody>
      </CCard>

      <CCard className="border-0 shadow-sm">
        <CCardHeader className="bg-white py-3 d-flex justify-content-between align-items-center">
            <span className="fw-bold">Horário Escolar</span>
        </CCardHeader>
        <CCardBody className="p-0">
            {renderCalendarContent()}
        </CCardBody>
      </CCard>

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