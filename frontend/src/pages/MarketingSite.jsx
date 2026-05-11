import React from 'react'
import { Navigate, Link } from 'react-router-dom'
import { CButton, CContainer, CRow, CCol } from '@coreui/react'
import { useAuthStore } from '../store'
import { getDefaultRouteForRole } from '../roleAccess'

/* -------- ILLUSTRAÇÕES (SVG inline, sem imagens) -------- */

function HeroComposition() {
  return (
    <div className="zen-hero-art">
      <div className="zen-hero-base" />
      <div className="zen-hero-layer-1" />
      <div className="zen-hero-layer-2" />
      <div className="zen-hero-accent-block" />
      <div className="zen-hero-vline zen-hero-vline-1" />
      <div className="zen-hero-vline zen-hero-vline-2" />
      <div className="zen-hero-hline" />
      <div className="zen-hero-dot zen-hero-dot-1" />
      <div className="zen-hero-dot zen-hero-dot-2" />
      <div className="zen-hero-dot zen-hero-dot-3" />
    </div>
  )
}

function IconClock() {
  return (
    <svg viewBox="0 0 64 64" fill="none" className="zen-icon">
      <circle cx="32" cy="32" r="28" stroke="var(--brand-800)" strokeWidth="2" fill="var(--brand-100)" />
      <line x1="32" y1="32" x2="32" y2="18" stroke="var(--brand-950)" strokeWidth="2.5" strokeLinecap="square" />
      <line x1="32" y1="32" x2="42" y2="38" stroke="var(--brand-500)" strokeWidth="2.5" strokeLinecap="square" />
      <circle cx="32" cy="32" r="3" fill="var(--brand-800)" />
    </svg>
  )
}

function IconSubstitution() {
  return (
    <svg viewBox="0 0 64 64" fill="none" className="zen-icon">
      <rect x="4" y="20" width="56" height="28" rx="0" fill="var(--brand-100)" stroke="var(--brand-800)" strokeWidth="2" />
      <rect x="12" y="28" width="16" height="14" rx="0" fill="var(--brand-800)" />
      <line x1="28" y1="35" x2="36" y2="35" stroke="var(--brand-500)" strokeWidth="2" />
      <polygon points="34,32 37,35 34,38" fill="var(--brand-500)" />
      <rect x="38" y="28" width="14" height="14" rx="0" fill="var(--brand-500)" />
    </svg>
  )
}

function IconEye() {
  return (
    <svg viewBox="0 0 64 64" fill="none" className="zen-icon">
      <rect x="4" y="4" width="56" height="56" rx="0" fill="var(--brand-100)" stroke="var(--brand-800)" strokeWidth="2" />
      <rect x="14" y="14" width="16" height="16" rx="0" fill="var(--brand-800)" />
      <rect x="34" y="14" width="16" height="16" rx="0" fill="var(--brand-100)" stroke="var(--brand-600)" strokeWidth="1" />
      <rect x="14" y="34" width="16" height="16" rx="0" fill="var(--brand-100)" stroke="var(--brand-500)" strokeWidth="1" />
      <rect x="34" y="34" width="16" height="16" rx="0" fill="var(--brand-500)" />
    </svg>
  )
}

function IconShield() {
  return (
    <svg viewBox="0 0 64 64" fill="none" className="zen-icon">
      <rect x="12" y="4" width="40" height="12" rx="0" fill="var(--brand-500)" />
      <rect x="4" y="18" width="56" height="4" rx="0" fill="var(--brand-100)" />
      <rect x="4" y="24" width="18" height="36" rx="0" fill="var(--brand-100)" stroke="var(--brand-800)" strokeWidth="2" />
      <rect x="26" y="24" width="34" height="36" rx="0" fill="var(--brand-50)" stroke="var(--brand-600)" strokeWidth="1" />
      <rect x="32" y="32" width="20" height="3" rx="0" fill="var(--brand-100)" />
      <rect x="32" y="40" width="20" height="3" rx="0" fill="var(--brand-100)" />
      <rect x="32" y="48" width="14" height="3" rx="0" fill="var(--brand-100)" />
      <rect x="32" y="52" width="20" height="6" rx="0" fill="var(--brand-500)" />
    </svg>
  )
}

function IconTarget() {
  return (
    <svg viewBox="0 0 64 64" fill="none" className="zen-icon">
      <rect x="4" y="4" width="56" height="56" rx="0" fill="var(--brand-50)" stroke="var(--brand-100)" strokeWidth="1" />
      <rect x="12" y="20" width="40" height="4" rx="0" fill="var(--brand-800)" />
      <rect x="12" y="28" width="36" height="4" rx="0" fill="var(--brand-500)" />
      <rect x="12" y="36" width="24" height="4" rx="0" fill="var(--brand-100)" />
      <rect x="12" y="44" width="30" height="4" rx="0" fill="var(--brand-100)" />
      <circle cx="48" cy="48" r="10" fill="var(--brand-800)" />
      <path d="M44 48 L47 51 L52 45" stroke="var(--brand-50)" strokeWidth="2" fill="none" />
    </svg>
  )
}

function IconFlow() {
  return (
    <svg viewBox="0 0 64 64" fill="none" className="zen-icon">
      <rect x="8" y="8" width="20" height="20" rx="0" fill="var(--brand-800)" />
      <rect x="10" y="10" width="16" height="3" rx="0" fill="var(--brand-500)" />
      <rect x="10" y="16" width="12" height="2" rx="0" fill="var(--brand-100)" />
      <rect x="10" y="20" width="8" height="2" rx="0" fill="var(--brand-100)" />
      <line x1="28" y1="18" x2="36" y2="18" stroke="var(--brand-500)" strokeWidth="2" />
      <polygon points="34,15 37,18 34,21" fill="var(--brand-500)" />
      <rect x="38" y="8" width="20" height="20" rx="0" fill="var(--brand-100)" stroke="var(--brand-800)" strokeWidth="2" />
      <rect x="40" y="10" width="16" height="3" rx="0" fill="var(--brand-500)" />
      <rect x="40" y="16" width="12" height="2" rx="0" fill="var(--brand-600)" />
      <rect x="40" y="20" width="10" height="2" rx="0" fill="var(--brand-600)" />
      <rect x="12" y="38" width="40" height="18" rx="0" fill="var(--brand-50)" stroke="var(--brand-800)" strokeWidth="2" />
      <rect x="16" y="42" width="14" height="10" rx="0" fill="var(--brand-500)" />
      <rect x="34" y="42" width="14" height="10" rx="0" fill="var(--brand-800)" />
      <text x="23" y="49" textAnchor="middle" fontFamily="Outfit, sans-serif" fontSize="6" fontWeight="700" fill="var(--brand-950)">OK</text>
    </svg>
  )
}

function IconRepair() {
  return (
    <svg viewBox="0 0 64 64" fill="none" className="zen-icon">
      <line x1="8" y1="18" x2="56" y2="18" stroke="var(--brand-100)" strokeWidth="2" />
      <rect x="8" y="8" width="48" height="8" rx="0" fill="var(--brand-800)" />
      <rect x="8" y="22" width="4" height="34" rx="0" fill="var(--brand-100)" />
      <line x1="8" y1="38" x2="56" y2="38" stroke="var(--brand-500)" strokeWidth="2" strokeDasharray="4 3" />
      <rect x="8" y="44" width="48" height="8" rx="0" fill="var(--brand-50)" stroke="var(--brand-100)" strokeWidth="1" />
      <rect x="8" y="56" width="48" height="4" rx="0" fill="var(--brand-100)" />
      <text x="56" y="13" textAnchor="end" fontFamily="Outfit, sans-serif" fontSize="5" fontWeight="600" fill="var(--brand-50)">PASSADO</text>
      <text x="32" y="36" textAnchor="middle" fontFamily="Outfit, sans-serif" fontSize="5" fontWeight="600" fill="var(--brand-800)">HOJE</text>
      <text x="56" y="49" textAnchor="end" fontFamily="Outfit, sans-serif" fontSize="5" fontWeight="600" fill="var(--brand-600)">RECALCULADO</text>
    </svg>
  )
}

function TimelineSVG() {
  return (
    <svg viewBox="0 0 720 180" fill="none" xmlns="http://www.w3.org/2000/svg" className="zen-timeline-art">
      {/* Eixo horizontal */}
      <line x1="40" y1="90" x2="680" y2="90" stroke="var(--brand-100)" strokeWidth="2" />
      
      {/* Semanas fixas (passado) */}
      {[0, 1, 2, 3, 4].map(i => {
        const cx = 100 + i * 75
        return (
          <g key={`past-${i}`}>
            <rect x={cx - 22} y={48} width="44" height="18" rx="0" fill="var(--brand-800)" />
            <text x={cx} y={61} textAnchor="middle" fontFamily="Outfit, sans-serif" fontSize="6" fontWeight="600" fill="var(--brand-50)">SEM {i + 1}</text>
            <circle cx={cx} cy="90" r="3" fill="var(--brand-800)" />
          </g>
        )
      })}
      
      {/* Linha divisória do HOJE */}
      <line x1="480" y1="40" x2="480" y2="140" stroke="var(--brand-500)" strokeWidth="2" strokeDasharray="6 4" />
      <rect x="462" y="35" width="36" height="16" rx="0" fill="var(--brand-500)" />
      <text x="480" y="47" textAnchor="middle" fontFamily="Outfit, sans-serif" fontSize="7" fontWeight="700" fill="var(--brand-950)">HOJE</text>
      
      {/* Semanas a recalcular (futuro) */}
      {[0, 1, 2].map(i => {
        const cx = 530 + i * 75
        return (
          <g key={`future-${i}`}>
            <rect x={cx - 22} y={48} width="44" height="18" rx="0" fill="var(--brand-100)" stroke="var(--brand-800)" strokeWidth="1.5" />
            <text x={cx} y={61} textAnchor="middle" fontFamily="Outfit, sans-serif" fontSize="6" fontWeight="600" fill="var(--brand-800)">SEM {6 + i}</text>
            <circle cx={cx} cy="90" r="3" fill="var(--brand-500)" />
          </g>
        )
      })}
      
      {/* Chaveta do passado preservado */}
      <path d="M40 120 L40 130 L475 130 L475 120" stroke="var(--brand-800)" strokeWidth="1.5" fill="none" />
      <text x="257" y="142" textAnchor="middle" fontFamily="Outfit, sans-serif" fontSize="7" fontWeight="600" fill="var(--brand-800)">AULAS JÁ LECIONADAS — PRESERVADAS</text>
      
      {/* Chaveta do futuro recalculado */}
      <path d="M490 155 L490 165 L680 165 L680 155" stroke="var(--brand-500)" strokeWidth="1.5" fill="none" />
      <text x="585" y="175" textAnchor="middle" fontFamily="Outfit, sans-serif" fontSize="7" fontWeight="600" fill="var(--brand-800)">RECALCULADO COM ALTERAÇÕES DA SEMANA</text>
    </svg>
  )
}

function StepsFlow() {
  return (
    <svg viewBox="0 0 720 120" fill="none" xmlns="http://www.w3.org/2000/svg" className="zen-steps-art">
      <line x1="170" y1="40" x2="540" y2="40" stroke="var(--brand-100)" strokeWidth="2" />
      <circle cx="120" cy="40" r="28" fill="var(--brand-100)" stroke="var(--brand-800)" strokeWidth="2" />
      <text x="120" y="45" textAnchor="middle" fontFamily="Playfair Display, serif" fontSize="20" fontWeight="700" fill="var(--brand-800)">1</text>
      <circle cx="360" cy="40" r="28" fill="var(--brand-100)" stroke="var(--brand-800)" strokeWidth="2" />
      <text x="360" y="45" textAnchor="middle" fontFamily="Playfair Display, serif" fontSize="20" fontWeight="700" fill="var(--brand-800)">2</text>
      <circle cx="600" cy="40" r="28" fill="var(--brand-100)" stroke="var(--brand-800)" strokeWidth="2" />
      <text x="600" y="45" textAnchor="middle" fontFamily="Playfair Display, serif" fontSize="20" fontWeight="700" fill="var(--brand-800)">3</text>
      <text x="120" y="90" textAnchor="middle" fontFamily="Outfit, sans-serif" fontSize="12" fontWeight="600" fill="var(--brand-800)" letterSpacing="0.08em">CONFIGURAR</text>
      <text x="360" y="90" textAnchor="middle" fontFamily="Outfit, sans-serif" fontSize="12" fontWeight="600" fill="var(--brand-800)" letterSpacing="0.08em">GERAR</text>
      <text x="600" y="90" textAnchor="middle" fontFamily="Outfit, sans-serif" fontSize="12" fontWeight="600" fill="var(--brand-800)" letterSpacing="0.08em">REPARAR</text>
    </svg>
  )
}

/* -------- DADOS -------- */

const outcomes = [
  { icon: <IconClock />, title: 'Horário do ano letivo em minutos', text: 'O que hoje consome semanas da sua direção fica resolvido numa tarde. E sempre que algo muda, recalcula em minutos o que antes implicava refazer tudo à mão.' },
  { icon: <IconRepair />, title: 'O horário adapta-se a cada semana', text: 'Módulos terminam, professores entram e saem, turmas reorganizam-se. O motor recalcula apenas o futuro, mantendo intacto o que já foi lecionado.' },
  { icon: <IconSubstitution />, title: 'Substituições resolvidas em segundos', text: 'Uma falta inesperada? O sistema recomenda o professor mais qualificado entre os disponíveis no momento. A decisão fica documentada.' },
  { icon: <IconEye />, title: 'Progresso curricular sempre visível', text: 'Cada UFCD, cada módulo — saiba exatamente quantas horas foram dadas, quantas faltam e se o ritmo permite terminar dentro do prazo.' },
  { icon: <IconTarget />, title: 'Horários que respeitam cada professor', text: 'Cada docente indica os seus bloqueios e preferências reais. O algoritmo otimiza com esses dados, não com suposições de gabinete.' },
  { icon: <IconShield />, title: 'Tudo documentado, sempre auditável', text: 'Sumários, faltas, substituições, fecho semanal — cada decisão fica registada. Quando a inspeção chegar, a sua escola está pronta.' }
]

const beforeAfterPairs = [
  {
    before: 'Cada alteração de horário obriga a refazer tudo manualmente. Horas perdidas a cada semana.',
    after: 'O motor recalcula apenas o período afetado, preservando o passado. A alteração está pronta em minutos.',
    label: 'Atualização Semanal'
  },
  {
    before: 'Falta um professor? Mensagens em cadeia, telefonemas e decisões à pressa sem saber quem está realmente disponível.',
    after: 'O sistema cruza competências com disponibilidade real no momento e recomenda o substituto certo. Tudo registado.',
    label: 'Gestão de Faltas'
  },
  {
    before: 'Fim de período: ninguém sabe ao certo que módulos foram dados, por quem, nem quanto falta para cumprir o programa.',
    after: 'Progresso de cada UFCD visível em tempo real. Horas dadas, em dívida, concluídas. O diretor sabe exatamente onde cada turma está.',
    label: 'Acompanhamento Curricular'
  }
]

const steps = [
  { num: '1', title: 'Configure a sua escola', text: 'Cursos, turmas, professores, salas, preferências de horário. Estruture a realidade da sua escola uma vez.' },
  { num: '2', title: 'Gere o horário completo', text: 'Um clique. O motor de otimização resolve milhares de variáveis respeitando cada restrição pedagógica e logística.' },
  { num: '3', title: 'Repare semana a semana', text: 'Algo mudou? Recalcule apenas da data de hoje em diante. O que já foi dado permanece. O futuro adapta-se.' }
]

/* -------- COMPONENTE PRINCIPAL -------- */

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

      {/* --- NAVEGAÇÃO --- */}
      <nav className="marketing-nav zen-reveal">
        <Link to="/" className="marketing-brand">
          <span className="marketing-brand-mark">A</span>
          <span className="text-display fw-bold" style={{ fontSize: '1.2rem', color: 'var(--brand-950)' }}>Aperius</span>
        </Link>
        <div className="marketing-nav-links d-none d-md-flex">
          <a href="#diferencial">O Diferencial</a>
          <a href="#ganhos">O que ganha</a>
          <a href="#investimento">Investimento</a>
        </div>
        <CButton href="#contacto" className="zen-btn-primary">Falar connosco</CButton>
      </nav>

      <main>
        {/* --- HERO --- */}
        <section className="zen-section-spacing zen-hero-section">
          <CContainer>
            <CRow className="align-items-center">
              <CCol lg={7} className="zen-reveal zen-stagger-1">
                <span className="zen-kicker">Software de gestão para escolas profissionais</span>
                <h1 className="text-display zen-hero-title">
                  O horário da sua escola muda todas as semanas.<br />
                  <span className="text-editorial">A ferramenta também.</span>
                </h1>
                <p className="zen-hero-lead">
                  No ensino profissional, um horário nunca está terminado. Módulos que fecham, turmas que se 
                  reorganizam, professores que entram e saem. O Aperius recalcula apenas o que mudou, 
                  preservando o que já foi dado. Sem refazer tudo. Sem perder o fio à meada curricular.
                </p>
              </CCol>
              <CCol lg={5} className="d-none d-lg-block zen-reveal zen-stagger-2">
                <HeroComposition />
              </CCol>
            </CRow>
          </CContainer>
        </section>

        {/* --- O DIFERENCIAL DO ENSINO PROFISSIONAL --- */}
        <section id="diferencial" className="zen-section-vision">
          <CContainer>
            <div className="zen-reveal" style={{ marginBottom: '3rem' }}>
              <div className="luxury-line mx-auto" />
              <h2 className="text-display text-center zen-vision-title">
                Ensino profissional não é <span className="text-editorial">ensino regular.</span>
              </h2>
              <p className="text-center" style={{ maxWidth: '640px', margin: '1.5rem auto 0', color: 'var(--brand-600)', fontSize: '1.05rem', lineHeight: '1.75' }}>
                Numa escola regular, o horário faz-se em setembro e dura o ano inteiro. Numa escola profissional, 
                cada semana traz alterações: um módulo de 25 horas termina a meio da semana, uma turma divide-se 
                em dois turnos, entra um formador externo. O que funciona para o regular <strong style={{ color: 'var(--brand-800)' }}>não funciona para si</strong>.
                E é exatamente por isso que o Aperius foi construído de raiz para a sua realidade.
              </p>
            </div>
            <div className="d-none d-md-block zen-reveal" style={{ marginBottom: '3rem' }}>
              <TimelineSVG />
            </div>
            <CRow className="zen-reveal">
              <CCol md={4} className="mb-3 mb-md-0">
                <div className="zen-diff-card">
                  <h3 className="text-display" style={{ fontSize: '1.3rem', marginBottom: '0.75rem', color: 'var(--brand-800)' }}>
                    O passado fica <span className="text-editorial">intacto.</span>
                  </h3>
                  <p style={{ fontSize: '0.92rem', lineHeight: '1.7', color: 'var(--brand-600)' }}>
                    Aulas já lecionadas, sumários registados, progresso curricular contabilizado. Nada se perde 
                    quando o horário muda. O motor respeita a fronteira do que já aconteceu.
                  </p>
                </div>
              </CCol>
              <CCol md={4} className="mb-3 mb-md-0">
                <div className="zen-diff-card">
                  <h3 className="text-display" style={{ fontSize: '1.3rem', marginBottom: '0.75rem', color: 'var(--brand-800)' }}>
                    O futuro <span className="text-editorial">adapta-se.</span>
                  </h3>
                  <p style={{ fontSize: '0.92rem', lineHeight: '1.7', color: 'var(--brand-600)' }}>
                    Módulos concluídos saem automaticamente da grelha. Novos professores, novas turmas, novas 
                    restrições — tudo entra na equação. O motor recalcula da data de hoje em diante.
                  </p>
                </div>
              </CCol>
              <CCol md={4}>
                <div className="zen-diff-card">
                  <h3 className="text-display" style={{ fontSize: '1.3rem', marginBottom: '0.75rem', color: 'var(--brand-800)' }}>
                    O ritmo <span className="text-editorial">mantém-se.</span>
                  </h3>
                  <p style={{ fontSize: '0.92rem', lineHeight: '1.7', color: 'var(--brand-600)' }}>
                    Com cada recalibração, o motor garante que o ritmo letivo se mantém. Projeta datas de fim 
                    realistas. Alerta se alguma turma está a ficar para trás. A direção decide com dados.
                  </p>
                </div>
              </CCol>
            </CRow>
          </CContainer>
        </section>

        {/* --- O QUE GANHA --- */}
        <section id="ganhos" className="zen-section-spacing">
          <CContainer>
            <div className="zen-reveal" style={{ marginBottom: '4rem' }}>
              <span className="zen-caps d-block mb-2">O que ganha</span>
              <h2 className="text-display" style={{ fontSize: '3rem' }}>
                Resultados <span className="text-editorial">concretos</span> para a sua escola.
              </h2>
            </div>
            <div className="zen-outcomes-grid">
              {outcomes.map((o, i) => (
                <div key={i} className={`zen-outcome-card zen-reveal zen-stagger-${Math.min(i + 1, 4)}`}>
                  {o.icon}
                  <h3 className="text-display zen-outcome-title">{o.title}</h3>
                  <p className="zen-outcome-text">{o.text}</p>
                </div>
              ))}
            </div>
          </CContainer>
        </section>

        {/* --- COMO FUNCIONA --- */}
        <section className="zen-section-dark">
          <CContainer>
            <div className="zen-reveal mb-5">
              <div className="luxury-line mb-4" style={{ background: 'var(--brand-500)' }} />
              <h2 className="text-display" style={{ fontSize: '3rem', color: 'var(--brand-50)' }}>
                Como <span className="text-editorial" style={{ color: 'var(--brand-500)' }}>funciona.</span>
              </h2>
            </div>
            <div className="d-none d-md-block zen-reveal">
              <StepsFlow />
            </div>
            <CRow className="mt-4">
              {steps.map((s, i) => (
                <CCol md={4} key={s.num} className={`zen-reveal zen-stagger-${i + 1}`}>
                  <div className="zen-step-card">
                    <span className="zen-step-num" style={{ borderColor: 'rgba(214,176,112,0.2)' }}>{s.num}</span>
                    <h3 className="text-display zen-step-title" style={{ color: 'var(--brand-50)' }}>{s.title}</h3>
                    <p className="zen-step-text" style={{ color: 'rgba(251,244,231,0.7)' }}>{s.text}</p>
                  </div>
                </CCol>
              ))}
            </CRow>
          </CContainer>
        </section>

        {/* --- ANTES vs DEPOIS --- */}
        <section className="zen-section-spacing">
          <CContainer>
            <div className="zen-reveal mb-5">
              <span className="zen-caps d-block mb-2">Antes e depois</span>
              <h2 className="text-display" style={{ fontSize: '3rem' }}>
                Da <span className="text-editorial">reação</span> à <span className="text-editorial">decisão.</span>
              </h2>
            </div>
            {beforeAfterPairs.map((pair, i) => (
              <CRow key={i} className={`mb-4 align-items-stretch zen-reveal zen-stagger-${i + 1}`}>
                <CCol md={6} className="mb-3 mb-md-0">
                  <div className="zen-before-block">
                    <span className="zen-ba-label zen-ba-label-before">Antes</span>
                    <span className="zen-caps d-block mb-2" style={{ color: 'var(--brand-500)', fontSize: '0.68rem' }}>{pair.label}</span>
                    <p className="zen-ba-text">{pair.before}</p>
                  </div>
                </CCol>
                <CCol md={6}>
                  <div className="zen-after-block">
                    <span className="zen-ba-label zen-ba-label-after">Depois</span>
                    <span className="zen-caps d-block mb-2" style={{ color: 'var(--brand-500)', fontSize: '0.68rem' }}>{pair.label}</span>
                    <p className="zen-ba-text">{pair.after}</p>
                  </div>
                </CCol>
              </CRow>
            ))}
          </CContainer>
        </section>

        {/* --- PARA CADA PESSOA --- */}
        <section className="zen-section-dark">
          <CContainer>
            <div className="zen-reveal mb-5">
              <div className="luxury-line mb-4" style={{ background: 'var(--brand-500)' }} />
              <h2 className="text-display" style={{ fontSize: '3rem', color: 'var(--brand-50)' }}>
                Feito para <span className="text-editorial" style={{ color: 'var(--brand-500)' }}>cada pessoa</span> da escola.
              </h2>
            </div>
            <CRow>
              <CCol md={6} className="zen-reveal zen-stagger-1 mb-4 mb-md-0">
                <div className="zen-role-card zen-role-card-dark">
                  <span className="zen-caps zen-role-label-dark">Para a Direção</span>
                  <ul className="zen-role-list">
                    <li>Horário do ano letivo gerado em minutos, atualizado sempre que necessário</li>
                    <li>Visibilidade total do progresso de cada UFCD em cada turma</li>
                    <li>Substituições com recomendação automática do professor mais qualificado</li>
                    <li>Fecho semanal validado com um clique — zero disparidades manuais</li>
                    <li>Rastreabilidade completa de cada decisão para auditoria e inspeção</li>
                    <li>Feriados, pausas letivas e grelha horária centralizados</li>
                  </ul>
                </div>
              </CCol>
              <CCol md={6} className="zen-reveal zen-stagger-2">
                <div className="zen-role-card zen-role-card-dark-teacher">
                  <span className="zen-caps zen-role-label-dark-teacher">Para o Professor</span>
                  <ul className="zen-role-list">
                    <li>Define os seus bloqueios e preferências de horário diretamente na plataforma</li>
                    <li>Vê o seu horário pessoal sempre atualizado com a versão mais recente</li>
                    <li>Regista sumários aula a aula, sem sair do ecrã do horário</li>
                    <li>Submete a semana com um clique — sem papéis, sem esquecimentos</li>
                    <li>Recebe notificações automáticas de substituições atribuídas</li>
                    <li>Histórico completo das suas aulas sempre acessível</li>
                  </ul>
                </div>
              </CCol>
            </CRow>
          </CContainer>
        </section>

        {/* --- TESTEMUNHO --- */}
        <section className="zen-section-testimonial">
          <CContainer>
            <div className="text-center py-5">
              <p className="zen-caps zen-testimonial-label">Quem usa, confirma</p>
              <blockquote className="text-display zen-testimonial-quote">
                "Deixámos de passar semanas a fazer horários para nos focarmos no que interessa: 
                a qualidade do ensino. O <span className="text-editorial zen-testimonial-highlight">Aperius</span> 
                trata da engenharia. Nós tratamos dos alunos."
              </blockquote>
            </div>
          </CContainer>
        </section>

        {/* --- INVESTIMENTO --- */}
        <section id="investimento" className="zen-section-spacing">
          <CContainer>
            <div className="mb-5 zen-reveal">
              <span className="zen-caps">Transparência</span>
              <h2 className="text-display" style={{ fontSize: '3rem' }}>
                Investimento com <span className="text-editorial">retorno visível.</span>
              </h2>
              <p style={{ maxWidth: '560px', color: 'var(--brand-600)', marginTop: '1rem' }}>
                Cada escola tem a sua dimensão e necessidades. Falamos consigo para entender o seu contexto 
                e apresentar uma proposta ajustada à sua realidade.
              </p>
            </div>
            <CRow className="g-4">
              {[
                { name: 'Escola Essencial', desc: 'Tudo o que uma direção precisa: horários dinâmicos, gestão de faltas, sumários e acompanhamento curricular em tempo real.' },
                { name: 'Rede Académica', desc: 'Gestão centralizada para agrupamentos e redes com múltiplos polos. Uma visão consolidada, várias escolas.' }
              ].map(p => (
                <CCol md={6} key={p.name} className="zen-reveal zen-stagger-1">
                  <div className="zen-pricing-card">
                    <h4 className="text-display zen-pricing-title">{p.name}</h4>
                    <p className="zen-pricing-desc">{p.desc}</p>
                    <div className="zen-pricing-bottom">
                      <span className="text-display zen-pricing-value">Sob consulta</span>
                      <CButton variant="ghost" className="zen-btn-ghost">Saber mais →</CButton>
                    </div>
                  </div>
                </CCol>
              ))}
            </CRow>
          </CContainer>
        </section>

        {/* --- CONTACTO --- */}
        <section id="contacto" className="zen-section-contact">
          <CContainer>
            <div className="zen-contact-box text-center zen-reveal">
              <h2 className="text-display mb-3">Vamos conversar?</h2>
              <p className="mb-4" style={{ maxWidth: '500px', margin: '0 auto 2rem' }}>
                Marque uma demonstração personalizada. Mostramos-lhe como o Aperius se adapta 
                à realidade da sua escola em menos de 30 minutos.
              </p>
              <CButton className="zen-btn-dark zen-btn-lg">
                Agendar Demonstração
              </CButton>
            </div>
          </CContainer>
        </section>
      </main>

      <footer className="zen-footer">
        <CContainer>
          <div className="zen-footer-inner">
            <span className="zen-caps zen-footer-copy">Aperius © 2026</span>
            <span className="text-editorial">Aperius — Feito para o Ensino Profissional.</span>
          </div>
        </CContainer>
      </footer>
    </div>
  )
}
