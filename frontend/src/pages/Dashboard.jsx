import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../apiClient'
import AnalyticsHeatmap from '../components/AnalyticsHeatmap'
import ReplacementModal from '../components/ReplacementModal'

// CoreUI
import { CButton, CCard, CCardBody, CCardHeader, CSpinner, CAlert, CContainer } from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilMediaPlay } from '@coreui/icons'

// FullCalendar
import FullCalendar from '@fullcalendar/react'
import timeGridPlugin from '@fullcalendar/timegrid'
import dayGridPlugin from '@fullcalendar/daygrid'
import interactionPlugin from '@fullcalendar/interaction'

// --- 1. FUNÇÕES API ---

const fetchAllData = async () => {
  // Vamos buscar TUDO o que precisamos em paralelo
  const [schedule, timeslots, rooms, lessons, subjects, classes, teachers] = await Promise.all([
    apiClient.get('/schedule/latest').then(r => r.data),
    apiClient.get('/import/timeslots').then(r => r.data),
    apiClient.get('/import/rooms').then(r => r.data),
    apiClient.get('/import/lessons').then(r => r.data),
    apiClient.get('/import/subjects').then(r => r.data),
    apiClient.get('/import/classes').then(r => r.data),
    apiClient.get('/import/teachers').then(r => r.data),
  ])
  return { schedule, timeslots, rooms, lessons, subjects, classes, teachers }
}

const generateSchedule = async () => {
  const response = await apiClient.post('/solver/generate')
  return response.data
}

// Helper: Converter Dados em Eventos do Calendário
// Helper: Converter Dados em Eventos do Calendário
const transformDataToEvents = (data) => {
  if (!data || !data.schedule) return []

  const today = new Date()
  const day = today.getDay()
  const diff = today.getDate() - day + (day === 0 ? -6 : 1) 
  const mondayBase = new Date(today.setDate(diff))
  
  return data.schedule.map(item => {
    const timeslot = data.timeslots.find(t => t.id === item.timeslot_id)
    const lesson = data.lessons.find(l => l.id === item.lesson_id)
    const room = data.rooms.find(r => r.id === item.room_id)
    
    if (!timeslot || !lesson) return null

    const subject = data.subjects.find(s => s.id === lesson.subject_id)?.name || '?'
    const className = data.classes.find(c => c.id === lesson.class_id)?.name || '?'
    const teacher = data.teachers.find(t => t.id === lesson.teacher_id)?.name || '?'
    const roomName = room ? room.name : '?'

    const eventDate = new Date(mondayBase)
    eventDate.setDate(mondayBase.getDate() + timeslot.day_of_week)
    const dateStr = eventDate.toISOString().split('T')[0]

    // --- ESPIÃO DE DEBUG ---
    if (teacher.includes("Patrícia")) {
        console.log("DEBUG PATRICIA:", {
            prof: teacher,
            materia: subject,
            horas: lesson.num_per_week,
            ehZero: lesson.num_per_week === 0
        })
    }

    // --- NOVA LÓGICA DE COR ---
    // Azul padrão (#321fdb)
    let bgColor = '#321fdb' 
    let borderColor = '#321fdb'

    // LÓGICA DE COR REFORÇADA:
    // Pinta de Laranja se num_per_week for 0 OU se a disciplina for "Substituição"
    if (lesson.num_per_week === 0 || subject === "Substituição") {
        bgColor = '#f9b115' 
        borderColor = '#f9b115'
    }
    // ---------------------------

    return {
      id: item.id,
      title: `${subject} (${className})`,
      start: `${dateStr}T${timeslot.start_time}`,
      end: `${dateStr}T${timeslot.end_time}`,
      
      extendedProps: {
        teacher_name: teacher,
        room_name: roomName,
        teacher_id: lesson.teacher_id,
        class_id: lesson.class_id,
        timeslot_id: item.timeslot_id
      },
      // Usamos as variáveis que definimos acima
      backgroundColor: bgColor,
      borderColor: borderColor
    }
  }).filter(Boolean)
}
// --- 3. COMPONENTE PRINCIPAL ---

const Dashboard = () => {
  const queryClient = useQueryClient()
  const [isGenerating, setIsGenerating] = useState(false)
  const [selectedEvent, setSelectedEvent] = useState(null) // O estado para o modal

  // QUERY: Buscar todos os dados
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['fullScheduleData'],
    queryFn: fetchAllData,
    refetchInterval: isGenerating ? 2000 : false
  })

  // MUTATION: Gerar
  const mutation = useMutation({
    mutationFn: generateSchedule,
    onSuccess: () => {
      setIsGenerating(true)
      setTimeout(() => setIsGenerating(false), 5000) 
    }
  })

  // --- A NOVA FUNÇÃO DE CLIQUE ---
  const handleEventClick = (clickInfo) => {
    // Guarda o evento clicado no estado, o que vai fazer o Modal abrir
    setSelectedEvent(clickInfo.event)
  }

  // Preparar eventos
  const events = data ? transformDataToEvents(data) : []

  const renderEventContent = (eventInfo) => {
    return (
      <div style={{fontSize: '0.85em', lineHeight: '1.2'}}>
        <b>{eventInfo.event.title}</b><br/>
        <i>{eventInfo.event.extendedProps.teacher_name}</i><br/> {/* Nota: teacher_name no novo helper */}
        <span className="badge bg-light text-dark mt-1">
          {eventInfo.event.extendedProps.room_name}
        </span>
      </div>
    )
  }

  return (
    <CContainer>
      <CCard className="mb-4 shadow-sm">
        <CCardHeader className="d-flex justify-content-between align-items-center bg-white py-3">
          <h4 className="m-0">O Meu Horário</h4>
          
          <CButton 
            color="primary" 
            onClick={() => mutation.mutate()} 
            disabled={mutation.isPending || isGenerating}
          >
            {mutation.isPending || isGenerating ? (
              <><CSpinner size="sm"/> A Gerar...</>
            ) : (
              <><CIcon icon={cilMediaPlay} className="me-2"/> Gerar Novo Horário</>
            )}
          </CButton>
        </CCardHeader>
        
        <CCardBody className="p-0">
          
          {/* MAPA DE CALOR */}
          <div className="p-3 border-bottom bg-light">
             <AnalyticsHeatmap />
          </div>

          {isLoading ? (
            <div className="text-center p-5"><CSpinner/> A carregar calendário...</div>
          ) : (
            <div className="p-3">
              {/* FULLCALENDAR */}
              <FullCalendar
                plugins={[timeGridPlugin, dayGridPlugin, interactionPlugin]}
                initialView="timeGridWeek"
                headerToolbar={{
                  left: 'prev,next today',
                  center: 'title',
                  right: 'timeGridWeek,dayGridMonth'
                }}
                weekends={true} 
                slotMinTime="08:00:00"
                slotMaxTime="19:00:00"
                allDaySlot={false}
                locale="pt" 
                events={events}
                eventContent={renderEventContent}
                height="auto"
                aspectRatio={1.8}
                // --- A NOVA PROP ---
                eventClick={handleEventClick} 
              />
            </div>
          )}
        </CCardBody>
      </CCard>

      {/* --- O NOVO MODAL --- */}
      {/* Ele só aparece se selectedEvent não for null */}
      <ReplacementModal 
        visible={!!selectedEvent} 
        eventData={selectedEvent} 
        onClose={() => setSelectedEvent(null)} 
      />

    </CContainer>
  )
}

export default Dashboard