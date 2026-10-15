import { useRef, useState } from 'react'
import { teacherWorkflowMoments } from '../../content/workflow'
import MarketingSection from '../shared/MarketingSection'
import SectionHeading from '../shared/SectionHeading'

function MomentVisual({ momentId }) {
  if (momentId === 'prepare') {
    return (
      <div className="cronos-teacher-workflow-visual cronos-teacher-workflow-visual--prepare" aria-hidden="true">
        <strong>Minha Disponibilidade</strong>
        <div className="cronos-teacher-preferences">
          {Array.from({ length: 15 }, (_, index) => <span className={index === 2 || index === 11 ? 'is-impossible' : index === 5 || index === 6 ? 'is-preferred' : ''} key={index} />)}
        </div>
        <small>Preferencial · Neutro · Evitar · Impossível</small>
      </div>
    )
  }

  if (momentId === 'teach') {
    return (
      <div className="cronos-teacher-workflow-visual cronos-teacher-workflow-visual--teach" aria-hidden="true">
        <div><span>10:30–12:00</span><span>Sala 2.12</span></div>
        <strong>Programação · 11.º TGPSI</strong>
        <label>Sumário</label>
        <p>Estruturas de dados e aplicação prática</p>
        <div><span className="is-primary">Aula dada</span><span>Sinalizar ocorrência</span></div>
      </div>
    )
  }

  return (
    <div className="cronos-teacher-workflow-visual cronos-teacher-workflow-visual--track" aria-hidden="true">
      <strong>Progresso das UFCDs</strong>
      <div><span>Programação</span><i><b style={{ width: '78%' }} /></i><small>78%</small></div>
      <div><span>Redes</span><i><b style={{ width: '64%' }} /></i><small>64%</small></div>
      <div><span>Sistemas</span><i><b style={{ width: '86%' }} /></i><small>86%</small></div>
    </div>
  )
}

export default function TeacherWorkflowSection() {
  const [activeId, setActiveId] = useState(teacherWorkflowMoments[0].id)
  const tabReferences = useRef([])
  const activeIndex = teacherWorkflowMoments.findIndex((moment) => moment.id === activeId)
  const activeMoment = teacherWorkflowMoments[activeIndex >= 0 ? activeIndex : 0]

  const handleTabKeyDown = (event, index) => {
    let nextIndex = index
    if (event.key === 'ArrowRight') nextIndex = (index + 1) % teacherWorkflowMoments.length
    if (event.key === 'ArrowLeft') nextIndex = (index - 1 + teacherWorkflowMoments.length) % teacherWorkflowMoments.length
    if (event.key === 'Home') nextIndex = 0
    if (event.key === 'End') nextIndex = teacherWorkflowMoments.length - 1
    if (nextIndex === index) return
    event.preventDefault()
    setActiveId(teacherWorkflowMoments[nextIndex].id)
    tabReferences.current[nextIndex]?.focus()
  }

  return (
    <MarketingSection className="cronos-teacher-workflow" labelledBy="cronos-teacher-workflow-title">
      <div className="cronos-container">
        <SectionHeading
          id="cronos-teacher-workflow-title"
          eyebrow="Área do professor"
          title="O professor mantém o contexto em cada aula"
          body="A disponibilidade, o horário ativo, os registos e o progresso seguem a mesma rotina."
          align="center"
        />
        <div className="cronos-teacher-workflow__tabs" role="tablist" aria-label="Momentos do professor">
          {teacherWorkflowMoments.map((moment, index) => {
            const isActive = moment.id === activeId
            return (
              <button
                key={moment.id}
                ref={(element) => { tabReferences.current[index] = element }}
                type="button"
                role="tab"
                id={`teacher-tab-${moment.id}`}
                aria-selected={isActive}
                aria-controls={`teacher-panel-${moment.id}`}
                tabIndex={isActive ? 0 : -1}
                onClick={() => setActiveId(moment.id)}
                onKeyDown={(event) => handleTabKeyDown(event, index)}
              >
                <span>0{index + 1}</span>{moment.label}
              </button>
            )
          })}
        </div>
        <div className="cronos-teacher-workflow__panel" role="tabpanel" id={`teacher-panel-${activeMoment.id}`} aria-labelledby={`teacher-tab-${activeMoment.id}`} tabIndex="0">
          <div className="cronos-teacher-workflow__copy">
            <h2>{activeMoment.title}</h2>
            <p>{activeMoment.text}</p>
            <ul className="cronos-check-list">
              {activeMoment.points.map((point) => <li key={point}>{point}</li>)}
            </ul>
            <div className="cronos-teacher-workflow__result"><strong>Resultado:</strong> {activeMoment.result}</div>
          </div>
          <MomentVisual momentId={activeMoment.id} />
        </div>
        <p className="cronos-teacher-workflow__boundary">A coordenação decide faltas e substituições.</p>
      </div>
    </MarketingSection>
  )
}
