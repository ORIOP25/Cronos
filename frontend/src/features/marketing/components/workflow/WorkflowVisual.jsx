const chapterBlocks = {
  prepare: [
    { class: 'is-course', label: 'Cursos & Turmas' },
    { class: 'is-room', label: 'Salas e equipamentos' },
    { class: 'is-teacher', label: 'Disponibilidade' },
    { class: 'is-calendar', label: 'Calendário Letivo' },
  ],
  adapt: [
    { class: 'is-protected', label: 'Passado Fixo' },
    { class: 'is-protected', label: 'Aulas Dadas' },
    { class: 'is-moving', label: 'Proposta Futura' },
    { class: 'is-moving', label: 'Reorganizado' },
  ],
  finish: [
    { class: 'is-complete', label: 'UFCD Concluída' },
    { class: 'is-complete', label: 'Horas Cumpridas' },
    { class: 'is-complete', label: 'Em Progresso' },
    { class: 'is-pending', label: 'Dívida a Recuperar' },
  ],
}

const chapterBadges = {
  prepare: 'Configuração Inicial',
  adapt: 'Recálculo em Tempo Real',
  finish: 'Acompanhamento de Horas',
}

export default function WorkflowVisual({ chapterId }) {
  const blocks = chapterBlocks[chapterId] || chapterBlocks.prepare
  const badge = chapterBadges[chapterId] || chapterBadges.prepare

  return (
    <div className={`cronos-workflow-visual cronos-workflow-visual--${chapterId}`} aria-hidden="true">
      <div className="cronos-workflow-visual__header">
        <span className="cronos-workflow-visual__badge">{badge}</span>
      </div>
      <div className="cronos-workflow-visual__axis">
        <span />
        <span />
        <span />
        <span />
      </div>
      <div className="cronos-workflow-visual__blocks">
        {blocks.map((block, index) => (
          <span className={block.class} key={`${chapterId}-${index}`}>
            <small>{block.label}</small>
          </span>
        ))}
      </div>
    </div>
  )
}
