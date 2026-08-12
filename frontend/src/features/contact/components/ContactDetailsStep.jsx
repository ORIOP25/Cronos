export default function ContactDetailsStep({ answers, errors, onChange, onNext }) {
  return (
    <form className="cronos-questionnaire__step" onSubmit={onNext} noValidate>
      <h2>Como podemos entrar em contacto?</h2>
      <div className="cronos-questionnaire__fields">
        <Field id="name" label="Nome" value={answers.name} error={errors.name} onChange={onChange} />
        <Field id="email" type="email" label="Email" value={answers.email} error={errors.email} onChange={onChange} />
        <Field id="phone" type="tel" label="Telefone, opcional" value={answers.phone} onChange={onChange} />
      </div>
      <button type="submit" className="cronos-button">Continuar</button>
    </form>
  )
}

function Field({ id, type = 'text', label, value, error, onChange }) {
  const errorId = `${id}-error`
  return (
    <label className="cronos-questionnaire__field" htmlFor={id}>
      <span>{label}{id === 'name' || id === 'email' ? ' *' : ''}</span>
      <input id={id} name={id} type={type} value={value} required={id === 'name' || id === 'email'} aria-invalid={Boolean(error)} aria-describedby={error ? errorId : undefined} onChange={(event) => onChange(id, event.target.value)} />
      {error && <small id={errorId}>{error}</small>}
    </label>
  )
}
