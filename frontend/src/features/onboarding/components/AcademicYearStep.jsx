export default function AcademicYearStep({ values, errors, onChange, onNext }) {
  return (
    <form className="guided-form__body" onSubmit={onNext} noValidate>
      <div>
        <h2 className="guided-form__heading">Quando decorre o ano letivo?</h2>
        <p className="guided-form__hint">A data final inclui exames e recuperações.</p>
      </div>
      <div className="guided-form__field">
        <label htmlFor="onboarding-school-start">Data de início</label>
        <input id="onboarding-school-start" type="date" value={values.school_start_date} onChange={(event) => onChange('school_start_date', event.target.value)} aria-invalid={Boolean(errors.school_start_date)} aria-describedby={errors.school_start_date ? 'onboarding-school-start-error' : undefined} />
        {errors.school_start_date && <p id="onboarding-school-start-error" className="guided-form__error">{errors.school_start_date}</p>}
      </div>
      <div className="guided-form__field">
        <label htmlFor="onboarding-school-end">Data-limite do ano letivo</label>
        <input id="onboarding-school-end" type="date" value={values.school_hard_end_date} onChange={(event) => onChange('school_hard_end_date', event.target.value)} aria-invalid={Boolean(errors.school_hard_end_date)} aria-describedby={errors.school_hard_end_date ? 'onboarding-school-end-error' : undefined} />
        {errors.school_hard_end_date && <p id="onboarding-school-end-error" className="guided-form__error">{errors.school_hard_end_date}</p>}
      </div>
      <div className="guided-form__actions"><span /><button type="submit" className="guided-form__primary">Continuar</button></div>
    </form>
  )
}
