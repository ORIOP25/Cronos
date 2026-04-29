import React from 'react'

// Componentes do Projeto
import AnalyticsHeatmap from '../components/AnalyticsHeatmap'

const Dashboard = () => {
  return (
    <div className="zen-reveal">
      <div className="d-flex justify-content-between align-items-end mb-5">
        <div>
          <span className="zen-caps" style={{ color: 'var(--brand-600)' }}>Visão Geral</span>
          <h1 className="text-display mt-2" style={{ fontSize: '3rem', color: 'var(--brand-950)' }}>
            Painel de <span className="text-editorial">Controlo</span>
          </h1>
        </div>
        <div className="luxury-line" style={{ width: '100px', marginBottom: '14px' }} />
      </div>

      <div className="zen-card zen-stagger-1">
        <div className="zen-card-header">
          <div className="d-flex align-items-center gap-2">
             <div style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: 'var(--brand-500)' }} />
             <h3 className="mb-0" style={{ fontSize: '1.1rem', fontWeight: '700', color: 'var(--brand-800)' }}>
               Disponibilidade Global
             </h3>
          </div>
          <span className="text-muted" style={{ fontSize: '0.8rem' }}>Atualizado em tempo real</span>
        </div>
        <div className="zen-card-body">
            <AnalyticsHeatmap />
        </div>
      </div>
    </div>
  )
}

export default Dashboard