export default function GuidedFormProgress({ current, total, onBack, backDisabled = false, className = '', trackClassName = '' }) {
  return (
    <div className={`guided-form-progress ${className}`.trim()}>
      <div className="guided-form-progress__row">
        <span>Passo {current} de {total}</span>
        {onBack && <button type="button" className="guided-form-progress__back" onClick={onBack} disabled={backDisabled}>← Voltar</button>}
      </div>
      <div className={`guided-form-progress__track ${trackClassName}`.trim()} role="progressbar" aria-valuenow={current} aria-valuemin="1" aria-valuemax={total} aria-label={`Passo ${current} de ${total}`} style={{ '--guided-form-progress': `${current / total * 100}%` }}><span /></div>
    </div>
  )
}
