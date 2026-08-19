export default function LunchWindowStep({ values, errors, onChange, onBack, onSubmit, pending }) {
  return (
    <form className="guided-form__body" onSubmit={onSubmit} noValidate>
      <div>
        <h2 className="guided-form__heading">Como funciona a pausa de almoço?</h2>
        <p className="guided-form__hint">A duração mínima deve caber dentro da janela configurada.</p>
      </div>
      <div className="guided-form__field">
        <label htmlFor="onboarding-lunch-start">Início da janela</label>
        <input id="onboarding-lunch-start" type="time" value={values.lunch_start} onChange={(event) => onChange('lunch_start', event.target.value)} aria-invalid={Boolean(errors.lunch_start)} aria-describedby={errors.lunch_start ? 'onboarding-lunch-start-error' : undefined} />
        {errors.lunch_start && <p id="onboarding-lunch-start-error" className="guided-form__error">{errors.lunch_start}</p>}
      </div>
      <div className="guided-form__field">
        <label htmlFor="onboarding-lunch-end">Fim da janela</label>
        <input id="onboarding-lunch-end" type="time" value={values.lunch_end} onChange={(event) => onChange('lunch_end', event.target.value)} aria-invalid={Boolean(errors.lunch_end)} aria-describedby={errors.lunch_end ? 'onboarding-lunch-end-error' : undefined} />
        {errors.lunch_end && <p id="onboarding-lunch-end-error" className="guided-form__error">{errors.lunch_end}</p>}
      </div>
      <div className="guided-form__field">
        <label htmlFor="onboarding-lunch-duration">Duração mínima</label>
        <input id="onboarding-lunch-duration" type="number" min="1" step="1" value={values.lunch_min_duration} onChange={(event) => onChange('lunch_min_duration', event.target.value === '' ? '' : Number(event.target.value))} aria-invalid={Boolean(errors.lunch_min_duration)} aria-describedby={errors.lunch_min_duration ? 'onboarding-lunch-duration-error' : undefined} />
        {errors.lunch_min_duration && <p id="onboarding-lunch-duration-error" className="guided-form__error">{errors.lunch_min_duration}</p>}
      </div>
      <div className="guided-form__actions"><button type="button" className="btn btn-link" onClick={onBack} disabled={pending}>Voltar</button><button type="submit" className="guided-form__primary" disabled={pending}>{pending ? 'A guardar' : 'Guardar e concluir'}</button></div>
    </form>
  )
}
