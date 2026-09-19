export default function GuidedFormProgress({ current, total, onBack, backDisabled = false, className = '', trackClassName = '' }) {
  const progressPercent = total > 1 ? ((current - 1) / (total - 1)) * 100 : 100
  const clampedProgressPercent = Math.max(0, Math.min(100, progressPercent))

  return (
    <div className={`guided-form-progress ${className}`.trim()}>
      <div className="guided-form-progress__row">
        <span>Passo {current} de {total}</span>
        {onBack && <button type="button" className="guided-form-progress__back" onClick={onBack} disabled={backDisabled}>← Voltar</button>}
      </div>
      <div className={`guided-form-progress__track ${trackClassName}`.trim()} role="progressbar" aria-valuenow={current} aria-valuemin="1" aria-valuemax={total} aria-label={`Passo ${current} de ${total}`} style={{ '--guided-form-progress': `${clampedProgressPercent}%` }}><span /></div>
    </div>
  )
}
