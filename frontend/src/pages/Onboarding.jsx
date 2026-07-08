import { useState, useEffect } from 'react'
import { useOrganization } from '@clerk/react'
import { useNavigate, Link } from 'react-router-dom'
import apiClient from '../apiClient'
import { getApiErrorMessage } from '../utils/apiErrors'

function toLocalDateInputValue(dateValue) {
  const year = dateValue.getFullYear()
  const month = String(dateValue.getMonth() + 1).padStart(2, '0')
  const day = String(dateValue.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const today = toLocalDateInputValue(new Date())
const nextYearDate = new Date()
nextYearDate.setFullYear(nextYearDate.getFullYear() + 1)
const nextYear = toLocalDateInputValue(nextYearDate)

function IconCalendar() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4" width="18" height="18" rx="2" />
      <line x1="16" y1="2" x2="16" y2="6" />
      <line x1="8" y1="2" x2="8" y2="6" />
      <line x1="3" y1="10" x2="21" y2="10" />
    </svg>
  )
}

function IconClock() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  )
}

export default function Onboarding() {
  const { organization } = useOrganization()
  const navigate = useNavigate()

  const [status, setStatus] = useState({ loading: true, complete: false })
  const [form, setForm] = useState({
    school_start_date: today,
    school_hard_end_date: nextYear,
    lunch_start: '12:30',
    lunch_end: '14:00',
    lunch_min_duration: 60,
  })
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    apiClient
      .get('/onboarding/status')
      .then((res) => {
        setStatus({ loading: false, complete: res.data.onboarding_complete })
        if (res.data.onboarding_complete) {
          navigate('/dashboard', { replace: true })
        }
      })
      .catch(() => setStatus({ loading: false, complete: false }))
  }, [navigate])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await apiClient.post('/onboarding', form)
      navigate('/dashboard', { replace: true })
    } catch (err) {
      setError(getApiErrorMessage(err, 'Erro ao guardar configurações. Tente novamente.'))
    } finally {
      setSubmitting(false)
    }
  }

  if (status.loading) {
    return (
      <div className="zen-onboarding-loading">
        <div className="zen-onboarding-loading-text">
          A preparar a sua escola&hellip;
        </div>
        <div className="zen-onboarding-progress">
          <div className="zen-onboarding-progress-dot active" />
          <div className="zen-onboarding-progress-line" />
          <div className="zen-onboarding-progress-dot" />
          <div className="zen-onboarding-progress-line" />
          <div className="zen-onboarding-progress-dot" />
        </div>
      </div>
    )
  }

  if (status.complete) {
    return (
      <div className="zen-onboarding-loading">
        <div className="zen-onboarding-loading-text">
          Configuração já concluída. A redirecionar&hellip;
        </div>
      </div>
    )
  }

  return (
    <div className="zen-onboarding-page">
      <div className="luxury-noise" style={{ opacity: 0.015 }} />

      <section className="zen-onboarding-hero zen-reveal">
        <div className="zen-onboarding-hero-inner">
          <span className="zen-onboarding-hero-kicker">Configuração inicial</span>
          <h1 className="zen-onboarding-hero-title">
            Bem-vindo,&nbsp;
            <span className="text-editorial" style={{ color: 'var(--brand-500)' }}>
              {organization?.name || 'Escola'}
            </span>
          </h1>
          <p className="zen-onboarding-hero-subtitle">
            Precisamos de algumas informações sobre o ano letivo para começar a
            gerar horários com precisão. São só dois passos.
          </p>
        </div>
      </section>

      <form onSubmit={handleSubmit} className="zen-onboarding-form">
        <div className="zen-onboarding-card zen-reveal zen-stagger-1">
          <div className="zen-onboarding-card-header">
            <div className="zen-onboarding-card-icon">
              <IconCalendar />
            </div>
            <h2 className="zen-onboarding-card-title">Ano Letivo</h2>
          </div>

          <div className="zen-onboarding-field">
            <label className="zen-onboarding-label">Data de início</label>
            <input
              type="date"
              aria-label="Data de início"
              className="zen-onboarding-input"
              value={form.school_start_date}
              onChange={(e) =>
                setForm({ ...form, school_start_date: e.target.value })
              }
              required
            />
          </div>

          <div className="zen-onboarding-row">
            <div className="zen-onboarding-field">
              <label className="zen-onboarding-label">
                Fim máximo{' '}
                <span style={{ fontWeight: 400, opacity: 0.5, textTransform: 'none', letterSpacing: '0' }}>
                  (exames | recuperações)
                </span>
              </label>
              <input
                type="date"
                aria-label="Fim máximo"
                className="zen-onboarding-input"
                value={form.school_hard_end_date}
                onChange={(e) =>
                  setForm({ ...form, school_hard_end_date: e.target.value })
                }
                required
              />
            </div>
          </div>
        </div>

        <div className="zen-onboarding-card zen-reveal zen-stagger-2">
          <div className="zen-onboarding-card-header">
            <div className="zen-onboarding-card-icon">
              <IconClock />
            </div>
            <h2 className="zen-onboarding-card-title">Janela de Almoço</h2>
          </div>

          <div className="zen-onboarding-row">
            <div className="zen-onboarding-field">
              <label className="zen-onboarding-label">Início</label>
              <input
                type="time"
                aria-label="Início do almoço"
                className="zen-onboarding-input"
                value={form.lunch_start}
                onChange={(e) =>
                  setForm({ ...form, lunch_start: e.target.value })
                }
                required
              />
            </div>

            <div className="zen-onboarding-field">
              <label className="zen-onboarding-label">Fim</label>
              <input
                type="time"
                aria-label="Fim do almoço"
                className="zen-onboarding-input"
                value={form.lunch_end}
                onChange={(e) =>
                  setForm({ ...form, lunch_end: e.target.value })
                }
                required
              />
            </div>
          </div>

          <div className="zen-onboarding-field" style={{ marginTop: 8 }}>
            <label className="zen-onboarding-label">Duração mínima (minutos)</label>
            <input
              type="number"
              aria-label="Duração mínima"
              className="zen-onboarding-input"
              style={{ maxWidth: 180 }}
              value={form.lunch_min_duration}
              min={30}
              max={120}
              onChange={(e) =>
                setForm({
                  ...form,
                  lunch_min_duration: Number.parseInt(e.target.value) || 60,
                })
              }
              required
            />
          </div>
        </div>

        {error && (
          <div className="zen-onboarding-error zen-reveal" role="alert">
            {error}
          </div>
        )}

        <div className="zen-onboarding-submit zen-reveal zen-stagger-3">
          <button
            type="submit"
            className="zen-btn-primary"
            disabled={submitting}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 10 }}
          >
            {submitting ? 'A guardar…' : 'Guardar e Começar'}
            <svg
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              style={{ opacity: submitting ? 0.5 : 1 }}
            >
              <path d="M6 4 L10 8 L6 12" />
            </svg>
          </button>
          <Link
            to="/dashboard"
            className="zen-auth-back-link"
            style={{ marginLeft: 24, fontWeight: 400 }}
          >
            Saltar por agora
          </Link>
        </div>
      </form>
    </div>
  )
}
