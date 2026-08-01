import {
  cilCalendar,
  cilLayers,
  cilClock,
  cilCheckCircle,
  cilEqualizer,
  cilShieldAlt,
  cilTask,
  cilMobile,
  cilBolt,
  cilSchool,
  cilEnvelopeClosed,
  cilPhone,
} from '@coreui/icons'

export const navItems = [
  { label: 'Início', href: '#inicio' },
  { label: 'Mais-valia', href: '#produto' },
  { label: 'Gerador', href: '#gerador' },
  { label: 'Rotina', href: '#rotina' },
  { label: 'Perfis', href: '#perfis' },
  { label: 'Sobre', href: '#sobre' },
  { label: 'Contacto', href: '#contacto' },
]

export const serviceTiles = [
  {
    title: 'Horários por turma e professor',
    text: 'Grelhas semanais com disciplinas, salas, professores e estado real de cada aula.',
    href: '#produto',
    icon: cilCalendar,
  },
  {
    title: 'Ocorrências e substituições',
    text: 'Faltas, furos, aulas dadas, substituições e decisões pendentes no mesmo fluxo.',
    href: '#rotina',
    icon: cilClock,
  },
  {
    title: 'UFCDs, módulos e progresso',
    text: 'Horas dadas e horas por cumprir acompanhadas por turma, disciplina e curso.',
    href: '#rotina',
    icon: cilLayers,
  },
  {
    title: 'Gerador adaptado ao profissional',
    text: 'Planeamento criado a partir de disponibilidade, salas, calendário e carga horária.',
    href: '#gerador',
    icon: cilEqualizer,
  },
]

export const productModules = [
  {
    title: 'Visão clara para a direção',
    text: 'Tome decisões com tranquilidade. Acompanhe o progresso das turmas, horas por cumprir e alertas da escola em tempo real, sem precisar de pedir ficheiros à equipa.',
    icon: cilShieldAlt,
  },
  {
    title: 'Horários sempre acessíveis',
    text: 'Cada professor acede ao seu horário no telemóvel ou computador. Se a sala mudar, toda a gente fica a saber no mesmo segundo.',
    icon: cilMobile,
  },
  {
    title: 'Imprevistos resolvidos sem stress',
    text: 'Faltou um professor às 8h15? Encontre logo um substituto disponível ou registe a alteração com um clique.',
    icon: cilBolt,
  },
  {
    title: 'O fim das folhas de sumários perdidas',
    text: 'Os docentes fecham a semana em poucos minutos, e a coordenação acompanha o cumprimento das UFCDs.',
    icon: cilTask,
  },
]

export const workflowSteps = [
  {
    number: '01',
    title: 'Preparar escola',
    text: 'Criar cursos profissionais, turmas, disciplinas, UFCDs/módulos, salas, professores, competências e calendário letivo.',
    icon: cilSchool,
  },
  {
    number: '02',
    title: 'Recolher disponibilidades',
    text: 'Cada professor indica quando pode ou prefere lecionar, incluindo horários impossíveis, a evitar, normais ou preferidos.',
    icon: cilCalendar,
  },
  {
    number: '03',
    title: 'Gerar horários',
    text: 'O Cronos cruza regras, carga horária, salas e disponibilidade para criar uma proposta que a escola pode rever antes de publicar.',
    icon: cilEqualizer,
  },
  {
    number: '04',
    title: 'Publicar horários',
    text: 'A escola consulta a grelha por turma ou professor e os docentes passam a registar aulas, sumários e ocorrências no próprio horário.',
    icon: cilCheckCircle,
  },
  {
    number: '05',
    title: 'Resolver imprevistos',
    text: 'Faltas, furos e substituições são tratadas com candidatos elegíveis, motivo da decisão e impacto nas horas por cumprir.',
    icon: cilClock,
  },
  {
    number: '06',
    title: 'Acompanhar progresso',
    text: 'A direção acompanha UFCDs, módulos, disciplinas e turmas para perceber o que já foi dado e o que ainda falta lecionar.',
    icon: cilLayers,
  },
]

export const generatorInputs = [
  'Cursos profissionais, turmas e anos de ciclo',
  'Disciplinas, UFCDs/módulos e horas totais',
  'Professores, competências e disponibilidade',
  'Salas, capacidade e tipo de sala',
  'Calendário escolar, feriados, pausas e almoço',
  'Horas já dadas e horas ainda por cumprir',
]

export const generatorOutputs = [
  'Horários harmoniosos e prontos a usar, sem choques de salas ou professores sobrecarregados',
  'Facilidade em fazer pequenos ajustes a meio da semana sem desmoronar tudo o resto',
]

export const routineChapters = [
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

export const roleCards = [
  {
    title: 'Direção',
    text: 'Durma com a tranquilidade de saber que todas as turmas estão a cumprir as horas exigidas e que a escola está em dia, com dados fiáveis à distância de um clique.',
    image: '/marketing/direcao-role.webp',
    fallbackImage: '/marketing/direcao-role.png',
  },
  {
    title: 'Secretaria e coordenação',
    text: 'Esqueça o cruzamento manual de 5 ficheiros Excel diferentes. Resolva furos, trocas e salas em segundos.',
    image: '/marketing/secretaria-role.webp',
    fallbackImage: '/marketing/secretaria-role.png',
  },
  {
    title: 'Professores',
    text: 'Um horário que cabe no bolso. Consulte a sua rotina, submeta sumários e indique a sua disponibilidade de forma intuitiva.',
    image: '/marketing/professores-role.webp',
    fallbackImage: '/marketing/professores-role.png',
  },
]

export const testimonials = [
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

export const contactCards = [
  { label: 'Email', value: 'contacto@cronos.pt', icon: cilEnvelopeClosed },
  { label: 'Telefone', value: '+351 210 000 000', icon: cilPhone },
]
