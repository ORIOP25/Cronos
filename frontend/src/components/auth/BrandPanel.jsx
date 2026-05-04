import React from 'react'
import PropTypes from 'prop-types'

/**
 * BrandPanel — painel de marca partilhado entre Login e Register.
 * Mostra o monograma HZ, nome da marca, tagline e estatísticas.
 *
 * Props:
 *   tagline — texto descritivo abaixo do nome da marca
 *   stats  — array de { value, label } para as 3 métricas
 */
const BrandPanel = ({ tagline, stats }) => {
  return (
    <div className="zen-login-brand-panel" style={{
      flex: '1 1 40%',
      position: 'relative',
      backgroundColor: 'var(--brand-950)',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '64px 40px',
      overflow: 'hidden',
      minHeight: '100vh',
    }}>
      {/* Grain texture */}
      <div className="luxury-noise" style={{ opacity: 0.03, zIndex: 1 }} />

      {/* Decorative elements */}
      <div style={{
        position: 'absolute',
        top: '15%',
        right: '15%',
        width: '180px',
        height: '180px',
        border: '1px solid rgba(214, 176, 112, 0.12)',
        transform: 'rotate(15deg)',
        zIndex: 1,
      }} />
      <div style={{
        position: 'absolute',
        bottom: '20%',
        left: '10%',
        width: '120px',
        height: '120px',
        border: '1px solid rgba(214, 176, 112, 0.08)',
        transform: 'rotate(-10deg)',
        zIndex: 1,
      }} />
      <div style={{
        position: 'absolute',
        top: '30%',
        left: '20%',
        width: '1px',
        height: '80px',
        background: 'var(--brand-500)',
        opacity: 0.2,
        zIndex: 1,
      }} />

      {/* Content */}
      <div style={{ position: 'relative', zIndex: 2, textAlign: 'center' }}>
        <div style={{
          width: '80px',
          height: '80px',
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          border: '2px solid var(--brand-500)',
          borderRadius: '50%',
          marginBottom: '28px',
        }}>
          <span style={{
            fontFamily: 'var(--font-display)',
            fontSize: '1.4rem',
            fontWeight: 700,
            color: 'var(--brand-500)',
            letterSpacing: '0.06em',
          }}>
            HZ
          </span>
        </div>

        <h2 className="text-display" style={{
          color: 'var(--brand-50)',
          fontSize: 'clamp(2rem, 4vw, 3rem)',
          marginBottom: '12px',
          letterSpacing: '-0.02em',
        }}>
          Horário{' '}
          <span style={{ color: 'var(--brand-500)' }}>Zen</span>
        </h2>

        <div style={{
          width: '40px',
          height: '1px',
          background: 'var(--brand-500)',
          margin: '16px auto 20px',
          opacity: 0.6,
        }} />

        <p style={{
          color: 'rgba(251, 244, 231, 0.5)',
          fontSize: '0.9rem',
          lineHeight: 1.7,
          maxWidth: '280px',
          margin: '0 auto 40px',
        }}>
          {tagline}
        </p>

        <div style={{
          display: 'flex',
          gap: '24px',
          justifyContent: 'center',
        }}>
          {stats.map((stat) => (
            <div key={stat.label} style={{ textAlign: 'center' }}>
              <div style={{
                fontFamily: 'var(--font-display)',
                fontSize: '1.5rem',
                color: 'var(--brand-500)',
                fontWeight: 700,
              }}>
                {stat.value}
              </div>
              <div style={{
                fontSize: '0.65rem',
                color: 'rgba(251, 244, 231, 0.35)',
                textTransform: 'uppercase',
                letterSpacing: '0.1em',
                marginTop: '4px',
              }}>
                {stat.label}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

BrandPanel.propTypes = {
  tagline: PropTypes.string.isRequired,
  stats: PropTypes.arrayOf(
    PropTypes.shape({
      value: PropTypes.string.isRequired,
      label: PropTypes.string.isRequired,
    })
  ).isRequired,
}

export default BrandPanel
