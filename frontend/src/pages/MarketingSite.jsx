import React from 'react'
import { Navigate, Link } from 'react-router-dom'
import { CButton, CContainer, CRow, CCol } from '@coreui/react'
import { useAuthStore } from '../store'
import { getDefaultRouteForRole } from '../roleAccess'

const features = [
  {
    number: '01',
    title: 'Substituições sem Ruído',
    text: 'A inteligência que resolve furos de última hora em segundos, respeitando a pedagogia e a disponibilidade real.',
    image: '/src/assets/marketing/substitutions_diagram.png'
  },
  {
    number: '02',
    title: 'Módulo a Módulo',
    text: 'Um acompanhamento cirúrgico do progresso curricular do Ensino Profissional. Sem planilhas perdidas.',
    image: 'https://images.unsplash.com/photo-1507314923564-d731b40280c6?auto=format&fit=crop&q=80&w=1200'
  },
  {
    number: '03',
    title: 'Memória Institucional',
    text: 'Um histórico inquebrável de todas as decisões tomadas. Transparência total para a direção e coordenação.',
    image: 'https://images.unsplash.com/photo-1434030216411-0b793f4b4173?auto=format&fit=crop&q=80&w=1200'
  }
]

export function PublicHomeGate() {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)
  const role = useAuthStore((state) => state.user?.role)

  if (isAuthenticated) {
    return <Navigate to={getDefaultRouteForRole(role)} replace />
  }
  return <MarketingSite />
}

export function MarketingSite() {
  return (
    <div className="marketing-page">
      {/* --- Navigation --- */}
      <nav className="marketing-nav zen-reveal">
        <Link to="/" className="marketing-brand" style={{ gap: '8px' }}>
          <span className="marketing-brand-mark" style={{ width: '40px', height: '40px' }}>HZ</span>
          <span className="text-display fw-bold" style={{ fontSize: '1.2rem', color: 'var(--brand-950)' }}>Horário Zen</span>
        </Link>
        <div className="marketing-nav-links zen-caps d-none d-md-flex">
          <a href="#vision">Visão</a>
          <a href="#experience">Experiência</a>
          <a href="#pricing">Investimento</a>
        </div>
        <CButton 
          href="#contact" 
          className="zen-caps" 
          style={{ 
            backgroundColor: 'var(--brand-800)', 
            color: 'white', 
            borderRadius: '0', 
            padding: '12px 28px',
            border: 'none'
          }}
        >
          Contactar
        </CButton>
      </nav>

      <main>
        {/* --- Hero Section --- */}
        <section className="zen-section-spacing">
          <CContainer>
            <CRow className="align-items-center">
              <CCol lg={7} className="zen-reveal zen-stagger-1">
                <span className="zen-caps text-secondary mb-3 d-block">Gestão de Escolas Profissionais</span>
                <h1 className="text-display mb-4" style={{ fontSize: 'clamp(3rem, 8vw, 6rem)', fontWeight: '700' }}>
                  A paz tem um <br /> <span className="text-editorial">novo método.</span>
                </h1>
                <p className="marketing-lead mb-5" style={{ fontSize: '1.25rem', opacity: 0.8 }}>
                  Desenhado para líderes que valorizam o silêncio operacional. 
                  Substituições inteligentes e progresso modular sem o caos das mensagens de última hora.
                </p>
                <div className="d-flex gap-3">
                  <CButton 
                    href="#contact"
                    style={{ 
                      backgroundColor: 'var(--brand-950)', 
                      color: 'white', 
                      borderRadius: '0', 
                      padding: '16px 40px',
                      fontSize: '0.9rem',
                      fontWeight: '600'
                    }}
                  >
                    Solicitar Apresentação
                  </CButton>
                </div>
              </CCol>
              <CCol lg={5} className="d-none d-lg-block zen-reveal zen-stagger-2">
                <div style={{ position: 'relative' }}>
                  <img 
                    src="https://images.unsplash.com/photo-1497366216548-37526070297c?auto=format&fit=crop&q=80&w=1200" 
                    alt="Atmosphere" 
                    style={{ width: '100%', height: '600px', objectFit: 'cover', filter: 'sepia(0.2) contrast(1.1)' }}
                  />
                  <div style={{ 
                    position: 'absolute', 
                    bottom: '-40px', 
                    left: '-40px', 
                    width: '200px', 
                    height: '200px', 
                    backgroundColor: 'var(--brand-500)',
                    zIndex: -1
                  }}></div>
                </div>
              </CCol>
            </CRow>
          </CContainer>
        </section>

        {/* --- Vision Statement --- */}
        <section id="vision" className="zen-section-spacing" style={{ backgroundColor: 'var(--brand-100)' }}>
          <CContainer>
            <div className="text-center zen-reveal">
              <div className="luxury-line mx-auto"></div>
              <h2 className="text-display mb-4" style={{ fontSize: '3rem' }}>O fim do <span className="text-editorial">improviso.</span></h2>
              <p className="mx-auto" style={{ maxWidth: '600px', fontSize: '1.1rem' }}>
                O Horário Zen não é apenas um software de substituições. É uma ferramenta de clareza institucional, 
                onde cada aula e cada módulo são acompanhados com o rigor que o Ensino Profissional exige.
              </p>
            </div>
          </CContainer>
        </section>

        {/* --- Experience Flow --- */}
        <section id="experience" className="zen-section-spacing">
          <CContainer>
            {features.map((f, i) => (
              <CRow key={f.number} className={`mb-5 pb-5 align-items-center ${i % 2 !== 0 ? 'flex-row-reverse' : ''} zen-reveal`}>
                <CCol md={6}>
                  <div style={{ overflow: 'hidden' }}>
                    <img 
                      src={f.image} 
                      alt={f.title} 
                      style={{ width: '100%', height: '450px', objectFit: 'cover' }}
                    />
                  </div>
                </CCol>
                <CCol md={5} className={i % 2 !== 0 ? 'me-auto' : 'ms-auto'}>
                  <span className="text-display mb-2 d-block" style={{ fontSize: '3rem', color: 'var(--brand-500)', opacity: 0.5 }}>{f.number}</span>
                  <h3 className="text-display mb-3" style={{ fontSize: '2.2rem' }}>{f.title}</h3>
                  <p style={{ fontSize: '1.05rem', lineHeight: '1.8' }}>{f.text}</p>
                </CCol>
              </CRow>
            ))}
          </CContainer>
        </section>

        {/* --- Quote / Authority --- */}
        <section className="zen-section-spacing" style={{ backgroundColor: 'var(--brand-950)', color: 'var(--brand-50)' }}>
          <CContainer>
            <div className="text-center py-5">
              <p className="zen-caps mb-4" style={{ color: 'var(--brand-500)' }}>Opinião da Direção</p>
              <blockquote className="text-display" style={{ fontSize: 'clamp(1.5rem, 3vw, 2.8rem)', maxWidth: '900px', margin: '0 auto', lineHeight: '1.3' }}>
                “A gestão de uma escola profissional exige rapidez, mas nunca à custa da qualidade pedagógica. 
                O <span className="text-editorial" style={{ color: 'var(--brand-500)' }}>Horário Zen</span> trouxe essa harmonia.”
              </blockquote>
            </div>
          </CContainer>
        </section>

        {/* --- Pricing / Investment --- */}
        <section id="pricing" className="zen-section-spacing">
          <CContainer>
            <div className="mb-5">
              <span className="zen-caps">Transparência</span>
              <h2 className="text-display" style={{ fontSize: '3rem' }}>Investimento em <span className="text-editorial">Calma.</span></h2>
            </div>
            <CRow className="g-4">
              {[
                { name: 'Escola Essencial', price: 'A consultar', desc: 'Para direções que precisam de ordem imediata.' },
                { name: 'Rede Académica', price: 'Sob medida', desc: 'Estrutura completa para gestão de múltiplos polos.' }
              ].map(p => (
                <CCol md={6} key={p.name}>
                  <div className="p-5" style={{ border: '1px solid var(--brand-100)', minHeight: '300px', display: 'flex', flexDirection: 'column' }}>
                    <h4 className="text-display mb-2" style={{ fontSize: '1.8rem' }}>{p.name}</h4>
                    <p className="text-muted">{p.desc}</p>
                    <div className="mt-auto pt-4">
                      <span className="text-display" style={{ fontSize: '1.5rem' }}>{p.price}</span>
                      <CButton variant="ghost" className="zen-caps ms-3" style={{ color: 'var(--brand-800)' }}>Saber mais →</CButton>
                    </div>
                  </div>
                </CCol>
              ))}
            </CRow>
          </CContainer>
        </section>

        {/* --- Contact --- */}
        <section id="contact" className="zen-section-spacing" style={{ backgroundColor: 'var(--brand-50)' }}>
          <CContainer>
            <div className="p-5 text-center" style={{ border: '1px solid var(--brand-500)' }}>
              <h2 className="text-display mb-4">Pronto para o próximo nível?</h2>
              <p className="mb-5">Marque uma conversa estratégica com um dos nossos consultores de gestão escolar.</p>
              <CButton 
                style={{ 
                  backgroundColor: 'var(--brand-950)', 
                  color: 'white', 
                  borderRadius: '0', 
                  padding: '16px 50px',
                  fontWeight: '600'
                }}
              >
                Agendar Reunião
              </CButton>
            </div>
          </CContainer>
        </section>
      </main>

      <footer className="py-5 border-top" style={{ borderColor: 'var(--brand-100)' }}>
        <CContainer>
          <div className="d-flex justify-content-between align-items-center">
            <span className="zen-caps" style={{ opacity: 0.5 }}>HZ © 2026</span>
            <span className="text-editorial">Horário Zen — Feito para Líderes.</span>
          </div>
        </CContainer>
      </footer>
    </div>
  )
}
