export default function QuestionnaireOptionStep({ title, field, options, value, errors, onSelect }) {
  const errorId = `${field}-error`
  return <div className="cronos-questionnaire__step"><h2>{title}</h2>{errors[field] && <p id={errorId} className="cronos-questionnaire__error" role="alert">{errors[field]}</p>}<div className="cronos-questionnaire__options" aria-describedby={errors[field] ? errorId : undefined}>{options.map((option) => <button key={option} type="button" className={value === option ? 'is-selected' : ''} onClick={() => onSelect(field, option)}>{option}</button>)}</div></div>
}
