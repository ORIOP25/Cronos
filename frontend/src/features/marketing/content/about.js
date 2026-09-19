import { publicIdentity } from './publicIdentity'

export const aboutContent = {
  eyebrow: 'Sobre o Cronos',
  title: 'Criado por quem conhece a rotina do Ensino Profissional',
  paragraphs: [
    'O Cronos nasceu para resolver um problema bem conhecido nas escolas: a complicação de gerir turmas profissionais com horários sobrepostos, salas ocupadas e horas por recuperar no fim do ano.',
    'Criei o Cronos para trazer ordem e agilidade a este processo, ligando a direção, a coordenação e os professores num só lugar simples de usar.',
  ],
  quote: 'O objetivo nunca foi apenas gerar horários, mas dar às escolas a tranquilidade que precisam para se focarem no essencial: o sucesso dos alunos.',
  founder: publicIdentity.operator.name,
  role: publicIdentity.operator.role,
  trust: {
    eyebrow: 'Uma ferramenta feita para a realidade portuguesa',
    title: 'Mais clareza para quem organiza o dia-a-dia da escola',
    paragraphs: [
      'O Cronos é uma plataforma de gestão criada para escolas profissionais em Portugal. Junta horários, faltas, substituições e acompanhamento de UFCDs num espaço comum para a direção, a coordenação e os professores.',
      'O produto é operado em Portugal com foco nas decisões concretas de quem gere uma escola: preservar o que já aconteceu, adaptar o futuro com critério e manter as horas letivas sob controlo.',
      'Para conhecer o produto, esclarecer uma dúvida ou marcar uma demonstração, fale diretamente com a equipa através do contacto público abaixo.',
    ],
  },
  image: { webpSrc: '/marketing/founder-portrait.webp', fallbackSrc: '/marketing/founder-portrait.png', alt: 'Retrato de Rodrigo Manguinhas, Fundador & CEO do Cronos.', width: 440, height: 550 },
}
