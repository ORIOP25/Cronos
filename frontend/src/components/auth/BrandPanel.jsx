const BrandPanel = ({ tagline, stats }) => {
  return (
    <div className="zen-auth-brand-side">
      <div className="luxury-noise" style={{ opacity: 0.025 }} />

      <div className="zen-auth-brand-geo">
        <div className="zen-auth-brand-geo-line zen-auth-brand-geo-line-1" />
        <div className="zen-auth-brand-geo-line zen-auth-brand-geo-line-2" />
        <div className="zen-auth-brand-geo-line zen-auth-brand-geo-line-3" />
        <div className="zen-auth-brand-geo-line zen-auth-brand-geo-line-4" />
        <div className="zen-auth-brand-geo-square zen-auth-brand-geo-square-1" />
        <div className="zen-auth-brand-geo-square zen-auth-brand-geo-square-2" />
        <div className="zen-auth-brand-geo-dot zen-auth-brand-geo-dot-1" />
        <div className="zen-auth-brand-geo-dot zen-auth-brand-geo-dot-2" />
        <div className="zen-auth-brand-geo-dot zen-auth-brand-geo-dot-3" />
        <div className="zen-auth-brand-geo-dot zen-auth-brand-geo-dot-4" />
      </div>

      <div className="zen-auth-brand-inner">
        <div className="zen-auth-monogram">
          <img src="/logo.png" alt="Cronos" className="zen-auth-logo" />
        </div>

        <h1 className="zen-auth-brand-name">Cronos</h1>

        <div className="zen-auth-divider" />

        <p className="zen-auth-tagline">{tagline}</p>

        <div className="zen-auth-stats">
          {stats.map((stat) => (
            <div key={stat.label} style={{ textAlign: 'center' }}>
              <div className="zen-auth-stat-value">{stat.value}</div>
              <div className="zen-auth-stat-label">{stat.label}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default BrandPanel
