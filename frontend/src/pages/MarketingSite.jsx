import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import './MarketingSite.css'

const navItems = [
  { label: 'Cronos', href: '#inicio' },
  { label: 'O que faz', href: '#produto' },
  { label: 'Gerador', href: '#gerador' },
  { label: 'Rotina', href: '#rotina' },
  { label: 'Perfis', href: '#perfis' },
  { label: 'Contacto', href: '#contacto' },
]

const serviceTiles = [
  {
    title: 'Horários por turma e professor',
    text: 'Grelhas semanais com disciplinas, salas, professores e estado real de cada aula.',
    href: '#produto',
  },
  {
    title: 'Ocorrências e substituições',
    text: 'Faltas, furos, aulas dadas, substituições e decisões pendentes no mesmo fluxo.',
    href: '#rotina',
  },
  {
    title: 'UFCDs, módulos e progresso',
    text: 'Horas dadas e horas por cumprir acompanhadas por turma, disciplina e curso.',
    href: '#rotina',
  },
  {
    title: 'Gerador adaptado ao profissional',
    text: 'Planeamento criado a partir de disponibilidade, salas, calendário e carga horária.',
    href: '#gerador',
  },
]

const productModules = [
  {
    title: 'Visão clara para a direção',
    text: 'Tome decisões com tranquilidade. Acompanhe o progresso das turmas, horas por cumprir e alertas da escola em tempo real, sem precisar de pedir ficheiros à equipa.',
  },
  {
    title: 'Horários sempre acessíveis',
    text: 'Cada professor acede ao seu horário no telemóvel ou computador. Se a sala mudar, toda a gente fica a saber no mesmo segundo.',
  },
  {
    title: 'Imprevistos resolvidos sem stress',
    text: 'Faltou um professor às 8h15? Encontre logo um substituto disponível ou registe a alteração com um clique.',
  },
  {
    title: 'O fim das folhas de sumários perdidas',
    text: 'Os docentes fecham a semana em poucos minutos, e a coordenação acompanha o cumprimento das UFCDs.',
  },
]

const workflowSteps = [
  {
    number: '01',
    title: 'Preparar a escola',
    text: 'Criar cursos profissionais, turmas, disciplinas, UFCDs/módulos, salas, professores, competências e calendário letivo.',
    icon: 'base',
  },
  {
    number: '02',
    title: 'Recolher disponibilidade',
    text: 'Cada professor indica quando pode ou prefere lecionar, incluindo horários impossíveis, a evitar, normais ou preferidos.',
    icon: 'flow',
  },
  {
    number: '03',
    title: 'Gerar e rever horários',
    text: 'O Cronos cruza regras, carga horária, salas e disponibilidade para criar uma proposta que a escola pode rever antes de publicar.',
    icon: 'mountain',
  },
  {
    number: '04',
    title: 'Publicar e operar',
    text: 'A escola consulta a grelha por turma ou professor e os docentes passam a registar aulas, sumários e ocorrências no próprio horário.',
    icon: 'flag',
  },
  {
    number: '05',
    title: 'Resolver imprevistos',
    text: 'Faltas, furos e substituições são tratadas com candidatos elegíveis, motivo da decisão e impacto nas horas por cumprir.',
    icon: 'flow',
  },
  {
    number: '06',
    title: 'Acompanhar progresso',
    text: 'A direção acompanha UFCDs, módulos, disciplinas e turmas para perceber o que já foi dado e o que ainda falta lecionar.',
    icon: 'base',
  },
]

const generatorInputs = [
  'Cursos profissionais, turmas e anos de ciclo',
  'Disciplinas, UFCDs/módulos e horas totais',
  'Professores, competências e disponibilidade',
  'Salas, capacidade e tipo de sala',
  'Calendário escolar, feriados, pausas e almoço',
  'Horas já dadas e horas ainda por cumprir',
]

const generatorOutputs = [
  'Horários harmoniosos e prontos a usar, sem choques de salas ou professores sobrecarregados',
  'Facilidade em fazer pequenos ajustes a meio da semana sem desmoronar tudo o resto',
]

const routineChapters = [
  {
    moment: 'Antes da semana começar',
    title: 'A escola prepara o terreno',
    story: 'Cursos, turmas, UFCDs, professores, salas, calendário e disponibilidade deixam de viver em mapas separados. A equipa começa a semana com a mesma base.',
    detailTitle: 'Fica pronto para decidir',
    items: [
      'Cursos profissionais com turmas por ano e ciclo.',
      'Disciplinas com UFCDs, módulos, códigos e horas.',
      'Professores ligados às disciplinas que podem lecionar.',
      'Salas com capacidade e tipo: normal, laboratório, ginásio ou artes.',
      'Grelha horária com dias, blocos, intervalos e almoço.',
      'Calendário letivo com feriados, pausas e períodos especiais.',
    ],
  },
  {
    moment: 'Quando o horário é publicado',
    title: 'Cada pessoa vê o que tem pela frente',
    story: 'A turma sabe onde estar. O professor sabe quando entra. A direção consegue perceber se a semana está equilibrada antes de começarem os pedidos de alteração.',
    detailTitle: 'Fica claro para todos',
    items: [
      'Horário semanal por turma.',
      'Horário semanal por professor.',
      'Propostas de horário revistas antes de publicar.',
      'Salas, disciplinas e docentes visíveis em cada bloco.',
      'Versão publicada separada do que ainda está em preparação.',
    ],
  },
  {
    moment: 'Quando o dia muda',
    title: 'O imprevisto deixa rasto',
    story: 'Uma falta, uma sala ocupada ou uma substituição de última hora não ficam perdidas numa mensagem. A decisão nasce na aula certa e mantém contexto.',
    detailTitle: 'Fica registado no horário',
    items: [
      'Ocorrências criadas a partir da própria aula.',
      'Furos, faltas, aulas dadas, substituições e reversões.',
      'Professores elegíveis para substituir quando faz sentido.',
      'Motivo da decisão e histórico consultável.',
      'Ajustes de última hora sem refazer todo o calendário.',
    ],
  },
  {
    moment: 'No fim da semana',
    title: 'A execução encontra o currículo',
    story: 'Os professores fecham sumários e notas. A direção deixa de adivinhar se a turma está no ritmo certo: vê horas dadas, horas por cumprir e UFCDs que pedem atenção.',
    detailTitle: 'Fica acompanhado até ao detalhe',
    items: [
      'Sumários e notas internas por aula.',
      'Fecho semanal, submissão e aprovação da semana do professor.',
      'Horas dadas e horas por cumprir por disciplina.',
      'Progresso por UFCD, módulo, turma e curso.',
      'Acesso dos professores ao seu horário, disponibilidade e registos.',
    ],
  },
]

const roleCards = [
  {
    title: 'Direção',
    text: 'Durma com a tranquilidade de saber que todas as turmas estão a cumprir as horas exigidas e que a escola está em dia, com dados fiáveis à distância de um clique.',
  },
  {
    title: 'Secretaria e coordenação',
    text: 'Esqueça o cruzamento manual de 5 ficheiros Excel diferentes. Resolva furos, trocas e salas em segundos.',
  },
  {
    title: 'Professores',
    text: 'Um horário que cabe no bolso. Consulte a sua rotina, submeta sumários e indique a sua disponibilidade de forma intuitiva.',
  },
]

const testimonials = [
  {
    name: 'Professor Ricardo',
    role: 'Coordenador pedagógico',
    quote: 'Antes, quando um docente faltava à primeira hora, a secretaria parava completamente. Hoje abrimos o Cronos, vemos quem está livre no edifício e resolvemos a substituição em 2 minutos.',
    avatar: 'R',
  },
  {
    name: 'Secretária Sofia',
    role: 'Administrativa',
    quote: "O maior alívio foi parar de perguntar 'qual é a versão mais recente do ficheiro?'. Agora toda a escola olha exatamente para o mesmo horário atualizado.",
    avatar: 'S',
  },
  {
    name: 'Professor Daniel',
    role: 'Docente',
    quote: 'Tenho o meu horário, sumários e submissão semanal no mesmo sítio. É simples perceber o que falta registar.',
    avatar: 'D',
  },
  {
    name: 'Diretora Helena',
    role: 'Direção escolar',
    quote: 'O Cronos dá-nos uma visão prática da execução letiva: horários, horas dadas, ocorrências e progresso por turma.',
    avatar: 'H',
  },
  {
    name: 'Coordenadora Marta',
    role: 'Coordenação de curso',
    quote: 'O acompanhamento por UFCD ficou mais claro. Quando uma turma atrasa, conseguimos identificar o problema cedo.',
    avatar: 'M',
  },
  {
    name: 'Secretário Luís',
    role: 'Serviços administrativos',
    quote: 'As alterações de última hora ficaram mais controladas. Cada decisão tem contexto e deixa histórico.',
    avatar: 'L',
  },
]

const contactCards = [
  { label: 'Email', value: 'suporte@cronos.pt', icon: 'mail' },
  { label: 'Telefone', value: '+351 210 000 000', icon: 'phone' },
  { label: 'Escritório', value: 'Lisboa, Portugal', icon: 'pin' },
]

function BrandMark() {
  return (
    <Link to="/" className="cronos-brand" aria-label="Cronos">
      <img src="/logo.png" alt="" className="cronos-brand__image" />
      <span className="cronos-brand__text">Cronos</span>
    </Link>
  )
}

function ArrowIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="cronos-arrow-icon">
      <path d="M5 12h13" />
      <path d="m13 6 6 6-6 6" />
    </svg>
  )
}

function ContactIcon({ type }) {
  if (type === 'phone') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M7 4h3l1.5 4-2 1.2a11 11 0 0 0 5.3 5.3l1.2-2 4 1.5v3a2 2 0 0 1-2 2A14 14 0 0 1 5 6a2 2 0 0 1 2-2Z" />
      </svg>
    )
  }

  if (type === 'pin') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 21s6-5.3 6-11a6 6 0 1 0-12 0c0 5.7 6 11 6 11Z" />
        <circle cx="12" cy="10" r="2" />
      </svg>
    )
  }

  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 6h16v12H4z" />
      <path d="m4 7 8 6 8-6" />
    </svg>
  )
}

function ProcessIcon({ type }) {
  if (type === 'base') {
    return (
      <svg viewBox="0 0 80 80" aria-hidden="true">
        <path d="M40 16v34" />
        <path d="M26 50h28" />
        <path d="m30 50 10-22 10 22" />
        <path d="M32 18h16" />
      </svg>
    )
  }

  if (type === 'mountain') {
    return (
      <svg viewBox="0 0 80 80" aria-hidden="true">
        <path d="M18 56 32 24l12 22 8-14 10 24Z" />
        <path d="m32 24 8 12" />
      </svg>
    )
  }

  if (type === 'flag') {
    return (
      <svg viewBox="0 0 80 80" aria-hidden="true">
        <path d="M24 62V20" />
        <path d="M24 22c12-8 20 8 32 0v24c-12 8-20-8-32 0" />
      </svg>
    )
  }

  return (
    <svg viewBox="0 0 80 80" aria-hidden="true">
      <path d="M20 28h34a8 8 0 1 0 0-16" />
      <path d="M60 52H26a8 8 0 1 0 0 16" />
      <path d="M20 40h40" />
      <circle cx="20" cy="28" r="5" />
      <circle cx="60" cy="40" r="5" />
      <circle cx="20" cy="52" r="5" />
    </svg>
  )
}

function Stars() {
  return (
    <div className="cronos-stars" aria-label="5 estrelas">
      <span>★</span>
      <span>★</span>
      <span>★</span>
      <span>★</span>
      <span>★</span>
    </div>
  )
}

export function MarketingSite() {
  const [activeReview, setActiveReview] = useState(0)
  const visibleTestimonials = [0, 1, 2].map((offset) => testimonials[(activeReview + offset) % testimonials.length])

  const goToPreviousReview = () => {
    setActiveReview((current) => (current - 1 + testimonials.length) % testimonials.length)
  }

  const goToNextReview = () => {
    setActiveReview((current) => (current + 1) % testimonials.length)
  }

  return (
    <div className="cronos-marketing">
      <header className="cronos-header" id="inicio">
        <div className="cronos-header__inner">
          <BrandMark />
          <nav className="cronos-nav" aria-label="Navegação principal">
            {navItems.map((item, index) => (
              <React.Fragment key={item.href}>
                <a href={item.href}>{item.label}</a>
                {index < navItems.length - 1 && <span aria-hidden="true">•</span>}
              </React.Fragment>
            ))}
          </nav>
          <div className="cronos-header__actions">
            <Link to="/login" className="cronos-login-link">Entrar</Link>
            <a href="#contacto" className="cronos-button cronos-button--header">
              Agendar demonstração
            </a>
          </div>
        </div>
        <span className="cronos-header__line" aria-hidden="true" />
      </header>

      <main>
        <section className="cronos-hero" aria-labelledby="cronos-hero-title">
          <div className="cronos-layout cronos-hero__grid">
            <div className="cronos-hero__copy">
              <h1 id="cronos-hero-title">
                Horários para o ensino profissional português.
              </h1>
              <span className="cronos-title-rule" aria-hidden="true" />
              <p>
                O Cronos é uma aplicação para escolas portuguesas com ensino profissional. Criámo-lo para aliviar a direção, a secretaria e os professores. Geramos horários sem conflitos em minutos, resolvemos furos de última hora e acompanhamos as horas das UFCDs num único lugar, de forma simples e transparente.
              </p>
              <div className="cronos-hero__actions">
                <a href="#contacto" className="cronos-button">
                  Marcar conversa de 15 minutos! <ArrowIcon />
                </a>
                <a href="#rotina" className="cronos-button cronos-button--secondary">
                  Ver como funcionará o meu dia a dia
                </a>
              </div>
            </div>

            <figure className="cronos-hero__visual">
              <img src="/marketing/hero-laptop.png" alt="Interface Cronos aberta num computador portátil" />
            </figure>
          </div>

          <div className="cronos-layout cronos-service-strip" aria-label="Principais áreas do Cronos">
            {serviceTiles.map((tile) => (
              <a href={tile.href} key={tile.title} className="cronos-service-tile">
                <span>{tile.title}</span>
                <small>{tile.text}</small>
                <ArrowIcon />
              </a>
            ))}
          </div>
        </section>

        <section className="cronos-product" id="produto" aria-labelledby="cronos-product-title">
          <div className="cronos-layout">
            <div className="cronos-section-heading cronos-section-heading--split">
              <h2 id="cronos-product-title">Porque o Cronos é uma mais-valia?</h2>
              <p>
                Sabemos que o ensino profissional é dinâmico e exigente. O Cronos liga o planeamento à sala de aula para que toda a equipa saiba exatamente onde está a cada momento.
              </p>
            </div>

            <div className="cronos-product-grid">
              {productModules.map((module) => (
                <article className="cronos-module-card" key={module.title}>
                  <h3>{module.title}</h3>
                  <p>{module.text}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="cronos-process" aria-labelledby="cronos-process-title">
          <div className="cronos-layout">
            <div className="cronos-process__intro">
              <div>
                <h2 id="cronos-process-title">
                  <span>Da preparação </span>
                  <strong>ao progresso UFCD</strong>
                </h2>
              </div>
              <p>
                Desenvolvemos o Cronos ao lado de coordenadores e diretores de escolas profissionais. Vimos de perto o cansaço de fechar mapas de UFCDs à mão e gerir substituições no WhatsApp. Por isso, desenhámos um fluxo natural que respeita as pessoas e o tempo de cada escola.
              </p>
            </div>

            <div className="cronos-process__cards cronos-process__cards--six">
              {workflowSteps.map((step) => (
                <article className="cronos-process-card" key={step.number}>
                  <div className="cronos-process-card__top">
                    <span>Etapa</span>
                    <strong>{step.number}</strong>
                  </div>
                  <ProcessIcon type={step.icon} />
                  <h3>{step.title}</h3>
                  <p>{step.text}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="cronos-generator" id="gerador" aria-labelledby="cronos-generator-title">
          <div className="cronos-layout cronos-generator__grid">
            <div className="cronos-generator__copy">
              <h2 id="cronos-generator-title">Um gerador que pensa como um coordenador.</h2>
              <p>
                Em vez de tentar adivinhar num quadrado em branco, diga ao Cronos o que tem na sua escola: salas disponíveis, dias preferidos dos professores e carga de cada UFCD. Nós fazemos as contas complexas por si.
              </p>
            </div>

            <div className="cronos-generator__panel">
              <div>
                <h3>O Cronos recebe</h3>
                <ul>
                  {generatorInputs.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
              <div>
                <h3>A escola recebe</h3>
                <ul>
                  {generatorOutputs.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </section>

        <section className="cronos-routine" id="rotina" aria-labelledby="cronos-routine-title">
          <div className="cronos-layout">
            <div className="cronos-section-heading cronos-section-heading--split">
              <h2 id="cronos-routine-title">A semana letiva, sem mapas soltos.</h2>
              <p>
                Seguimos uma semana real numa escola profissional: o que se prepara, o que se publica, o que muda e o que fica registado para a direção acompanhar.
              </p>
            </div>

            <div className="cronos-routine-grid">
              {routineChapters.map((chapter) => (
                <article className="cronos-routine-card" key={chapter.title}>
                  <div className="cronos-routine-card__scene">
                    <span>{chapter.moment}</span>
                    <h3>{chapter.title}</h3>
                    <p>{chapter.story}</p>
                  </div>
                  <div className="cronos-routine-card__details">
                    <strong>{chapter.detailTitle}</strong>
                    <ul>
                      {chapter.items.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="cronos-roles" id="perfis" aria-labelledby="cronos-roles-title">
          <div className="cronos-layout">
            <div className="cronos-section-heading cronos-section-heading--center">
              <h2 id="cronos-roles-title">Cada perfil sabe o que tem de fazer.</h2>
              <p>
                O Cronos separa responsabilidades sem separar informação. A direção acompanha, a secretaria organiza e os professores executam o registo diário.
              </p>
            </div>
            <div className="cronos-role-grid">
              {roleCards.map((role) => (
                <article className="cronos-role-card" key={role.title}>
                  <h3>{role.title}</h3>
                  <p>{role.text}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="cronos-product-panorama" aria-label="Visão visual do produto Cronos">
          <img src="/marketing/product-panorama.png" alt="Visão composta dos horários, progresso e disciplinas no Cronos" />
        </section>

        <section className="cronos-testimonials" id="testemunhos" aria-labelledby="cronos-testimonials-title">
          <div className="cronos-layout">
            <div className="cronos-testimonials__heading">
              <h2 id="cronos-testimonials-title">
                Histórias de escolas que precisam de controlo real.
              </h2>
            </div>

            <div className="cronos-testimonials__wrap">
              <button className="cronos-carousel-button" type="button" aria-label="Testemunho anterior" onClick={goToPreviousReview}>
                ‹
              </button>
              <div className="cronos-testimonial-grid">
                {visibleTestimonials.map((testimonial) => (
                  <article className="cronos-testimonial-card" key={testimonial.name}>
                    <div className="cronos-avatar" aria-hidden="true">{testimonial.avatar}</div>
                    <h3>{testimonial.name}</h3>
                    <p className="cronos-testimonial-card__role">{testimonial.role}</p>
                    <Stars />
                    <blockquote>
                      <span aria-hidden="true">“</span>
                      {testimonial.quote}
                      <span aria-hidden="true">”</span>
                    </blockquote>
                  </article>
                ))}
              </div>
              <button className="cronos-carousel-button" type="button" aria-label="Testemunho seguinte" onClick={goToNextReview}>
                ›
              </button>
            </div>

            <div className="cronos-carousel-dots" aria-label="Escolher testemunho">
              {testimonials.map((testimonial, index) => (
                <button
                  key={testimonial.name}
                  type="button"
                  className={index === activeReview ? 'is-active' : ''}
                  aria-label={`Mostrar testemunhos a partir de ${testimonial.name}`}
                  onClick={() => setActiveReview(index)}
                />
              ))}
            </div>
            <span className="cronos-testimonials__scribble" aria-hidden="true" />
          </div>
        </section>

        <section className="cronos-contact" id="contacto" aria-labelledby="cronos-contact-title">
          <div className="cronos-layout cronos-contact__grid">
            <div className="cronos-contact__content">
              <h2 id="cronos-contact-title">Gostava de ver como funcionaria na sua escola? Fale connosco.</h2>
              <p>
                Sem compromisso. Mostre-nos o seu maior desafio com os horários atuais e mostramos-lhe, em 15 minutos, como o Cronos pode ajudar a resolvê-lo.
              </p>

              <div className="cronos-contact-cards">
                {contactCards.map((card) => (
                  <div className="cronos-contact-card" key={card.label}>
                    <span className="cronos-contact-card__icon">
                      <ContactIcon type={card.icon} />
                    </span>
                    <div>
                      <strong>{card.label}</strong>
                      <span>{card.value}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <form className="cronos-form" aria-label="Formulário de contacto" onSubmit={(event) => event.preventDefault()}>
              <label className="cronos-field cronos-field--full">
                <span>O seu nome</span>
                <input type="text" name="name" placeholder="Nome completo" />
              </label>
              <label className="cronos-field">
                <span>Endereço de email</span>
                <input type="email" name="email" placeholder="exemplo@escola.pt" />
              </label>
              <label className="cronos-field">
                <span>Número de telefone</span>
                <input type="tel" name="phone" placeholder="+351 912 345 678" />
              </label>
              <label className="cronos-field cronos-field--full">
                <span>Assunto</span>
                <select name="subject" defaultValue="">
                  <option value="" disabled>Selecione uma opção</option>
                  <option value="demo">Agendar demonstração</option>
                  <option value="diagnostico">Diagnóstico de horários</option>
                  <option value="proposta">Pedido de proposta</option>
                </select>
              </label>
              <label className="cronos-field cronos-field--full">
                <span>Conte-nos um pouco sobre a sua escola (Ex.: quantas turmas têm ou qual a maior dificuldade atualmente)</span>
                <textarea name="message" placeholder="Conte-nos aqui sobre a sua escola e desafios..." rows="4" />
              </label>
              <label className="cronos-checkbox">
                <input type="checkbox" name="newsletter" />
                <span>Desejo receber novidades sobre o Cronos</span>
              </label>
              <button type="submit" className="cronos-button cronos-button--form">
                Falar com a nossa equipa <ArrowIcon />
              </button>
              <p className="cronos-form__note">Respondemos habitualmente em menos de 2 horas.</p>
            </form>
          </div>
        </section>
      </main>

      <footer className="cronos-footer">
        <div className="cronos-layout">
          <div className="cronos-footer__brand">Cronos.</div>
          <div className="cronos-footer__grid">
            <div>
              <h2>Sede</h2>
              <p>Cronos Software</p>
              <p>Rua do Tempo, 100</p>
              <p>Lisboa, Portugal</p>
            </div>
            <div>
              <h2>Navegação</h2>
              {navItems.map((item) => (
                <a href={item.href} key={item.href}>{item.label}</a>
              ))}
            </div>
            <div>
              <h2>Contacto</h2>
              <p>suporte@cronos.pt</p>
              <p>+351 210 000 000</p>
              <p>vendas@cronos.pt</p>
            </div>
            <div>
              <h2>Presença</h2>
              <a href="https://www.linkedin.com" target="_blank" rel="noreferrer">LinkedIn</a>
              <a href="https://twitter.com" target="_blank" rel="noreferrer">Twitter</a>
              <a href="https://github.com" target="_blank" rel="noreferrer">GitHub</a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}
