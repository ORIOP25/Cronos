import { teacherScheduleHub, teacherUncertainty } from '../../content/home'
import MarketingSection from '../shared/MarketingSection'
import Reveal from '../shared/Reveal'
import SectionHeading from '../shared/SectionHeading'

const dayLabels = ['SEG', 'TER', 'QUA', 'QUI', 'SEX']
const timeLabels = ['08:30', '10:30', '13:30']

function TeacherPainVisual() {
  return (
    <Reveal className="cronos-teacher-pain__visual">
      <div className="cronos-teacher-pain__lesson">
        <span>Terça-feira</span>
        <strong>10:30 · Programação</strong>
      </div>
      <div className="cronos-teacher-pain__versions">
        {teacherUncertainty.versions.map((version) => (
          <article className={`cronos-teacher-version cronos-teacher-version--${version.id}`} key={version.id}>
            <span>{version.label}</span>
            <strong>{version.room}</strong>
            <small>{version.state}</small>
          </article>
        ))}
      </div>
      <p>Qual é a versão certa?</p>
    </Reveal>
  )
}

function TeacherSchedule() {
  return (
    <div className="cronos-teacher-schedule">
      <div className="cronos-teacher-schedule__header">
        <strong>O meu horário</strong>
        <span>Atualizado</span>
      </div>
      <div className="cronos-teacher-schedule__scroll">
        <div className="cronos-teacher-schedule__grid" aria-hidden="true">
          <span />
          {dayLabels.map((day) => <strong key={day}>{day}</strong>)}
          {timeLabels.map((time, rowIndex) => (
            <div className="cronos-teacher-schedule__row" key={time}>
              <span>{time}</span>
              {dayLabels.map((day) => <i key={`${day}-${time}`} />)}
              {teacherScheduleHub.blocks.filter((block) => block.row === rowIndex + 1).map((block) => (
                <b key={block.id} style={{ gridColumn: block.day + 1, gridRow: 1 }}>
                  {block.label}<small>{block.className}</small>
                </b>
              ))}
            </div>
          ))}
        </div>
      </div>
      <div className="cronos-teacher-schedule__footer">
        <span>Versão ativa</span>
        <span>Semana pronta para registar</span>
      </div>
    </div>
  )
}

function ActionList({ actions, side }) {
  return (
    <div className={`cronos-teacher-hub__actions cronos-teacher-hub__actions--${side}`}>
      {actions.map((action) => (
        <article className="cronos-teacher-action" key={action.id}>
          <span aria-hidden="true" />
          <h3>{action.title}</h3>
          <p>{action.text}</p>
        </article>
      ))}
    </div>
  )
}

export default function TeacherExperienceSections() {
  return (
    <>
      <MarketingSection className="cronos-teacher-pain" labelledBy="cronos-teacher-pain-title">
        <div className="cronos-container cronos-teacher-pain__grid">
          <SectionHeading
            id="cronos-teacher-pain-title"
            eyebrow={teacherUncertainty.eyebrow}
            title={teacherUncertainty.title}
            body={teacherUncertainty.body}
          />
          <TeacherPainVisual />
        </div>
      </MarketingSection>

      <MarketingSection className="cronos-teacher-hub" labelledBy="cronos-teacher-hub-title">
        <div className="cronos-container">
          <SectionHeading
            id="cronos-teacher-hub-title"
            eyebrow="Uma rotina clara"
            title={teacherScheduleHub.title}
            body={teacherScheduleHub.body}
            align="center"
          />
          <div className="cronos-teacher-hub__layout" role="region" aria-label="Horário e rotina do professor">
            <ActionList actions={teacherScheduleHub.actions.slice(0, 2)} side="left" />
            <TeacherSchedule />
            <ActionList actions={teacherScheduleHub.actions.slice(2)} side="right" />
          </div>
        </div>
      </MarketingSection>
    </>
  )
}
