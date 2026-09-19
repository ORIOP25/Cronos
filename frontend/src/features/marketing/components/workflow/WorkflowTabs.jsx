import { useRef, useState } from 'react'
import CIconModule from '@coreui/icons-react'
import { cilCalendar, cilCheckCircle, cilLayers } from '@coreui/icons'
import MarketingSection from '../shared/MarketingSection'
import SectionHeading from '../shared/SectionHeading'
import { workflowChapters } from '../../content/workflow'
import WorkflowVisual from './WorkflowVisual'

const CIcon = CIconModule.CIcon ?? CIconModule.default ?? CIconModule

const chapterIcons = { prepare: cilCalendar, adapt: cilCheckCircle, finish: cilLayers }

export default function WorkflowTabs() {
  const [activeId, setActiveId] = useState(workflowChapters[0].id)
  const tabReferences = useRef([])
  const activeIndex = workflowChapters.findIndex((chapter) => chapter.id === activeId)
  const activeChapter = workflowChapters[activeIndex >= 0 ? activeIndex : 0]

  const selectTab = (chapterId) => setActiveId(chapterId)
  const handleTabKeyDown = (event, index) => {
    let nextIndex = index
    if (event.key === 'ArrowRight') nextIndex = (index + 1) % workflowChapters.length
    if (event.key === 'ArrowLeft') nextIndex = (index - 1 + workflowChapters.length) % workflowChapters.length
    if (event.key === 'Home') nextIndex = 0
    if (event.key === 'End') nextIndex = workflowChapters.length - 1
    if (nextIndex === index) return
    event.preventDefault()
    setActiveId(workflowChapters[nextIndex].id)
    tabReferences.current[nextIndex]?.focus()
  }

  return (
    <MarketingSection className="cronos-workflow" labelledBy="cronos-workflow-title">
      <div className="cronos-container">
        <SectionHeading
          as="h1"
          variant="page"
          id="cronos-workflow-title"
          eyebrow="Como funciona"
          title="O Cronos ajusta o horário à rotina da escola"
          body="Explore os três momentos que ligam preparação, mudança e acompanhamento."
          align="center"
        />
        <div className="cronos-workflow__experience">
          <div className="cronos-tabs" role="tablist" aria-label="Capítulos do Cronos">
            {workflowChapters.map((chapter, index) => {
              const isActive = chapter.id === activeId
              return (
                <button
                  key={chapter.id}
                  ref={(element) => { tabReferences.current[index] = element }}
                  type="button"
                  role="tab"
                  id={`tab-${chapter.id}`}
                  aria-selected={isActive}
                  aria-controls={`panel-${chapter.id}`}
                  tabIndex={isActive ? 0 : -1}
                  onClick={() => selectTab(chapter.id)}
                  onKeyDown={(event) => handleTabKeyDown(event, index)}
                >
                  <span className="cronos-tabs__number">0{index + 1}</span>
                  <CIcon icon={chapterIcons[chapter.id]} />
                  <span className="cronos-tabs__label">{chapter.label}</span>
                </button>
              )
            })}
          </div>
          <div
            className="cronos-workflow__panel"
            role="tabpanel"
            id={`panel-${activeChapter.id}`}
            aria-labelledby={`tab-${activeChapter.id}`}
            tabIndex="0"
          >
            <div className="cronos-workflow__copy">
              <h2>{activeChapter.title}</h2>
              <p>{activeChapter.text}</p>
              <ul className="cronos-check-list">
                {activeChapter.points.map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ul>
              <div className="cronos-workflow__result">
                <strong>Resultado:</strong> {activeChapter.result}
              </div>
            </div>
            <WorkflowVisual chapterId={activeChapter.id} />
          </div>
        </div>
      </div>
    </MarketingSection>
  )
}
