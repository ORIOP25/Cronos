export const TUTORIAL_VERSION = 1
export const TUTORIAL_STORAGE_PREFIX = `cronos:tutorial:v${TUTORIAL_VERSION}`

export const getTutorialStorageKey = (clerkUserId, clerkOrgId) => {
  const user = clerkUserId || 'anonymous'
  const org = clerkOrgId || 'personal'
  return `${TUTORIAL_STORAGE_PREFIX}:user:${user}:org:${org}`
}

export const TUTORIAL_STEPS = Object.freeze([
  { id: 'structure_overview', chapter: 1, stepNumber: 1, isSkippable: false, title: 'Estrutura da escola', description: 'Conheça a sequência de configuração que prepara uma escola para o primeiro horário.', actionType: 'CONTINUE' },
  { id: 'subject_create', chapter: 1, stepNumber: 2, isSkippable: true, title: 'Criar disciplina', description: 'Guarde uma disciplina preparada na simulação local.', actionType: 'SAVE' },
  { id: 'module_add', chapter: 1, stepNumber: 3, isSkippable: true, title: 'Adicionar módulo', description: 'Adicione um módulo com carga horária positiva.', actionType: 'SAVE' },
  { id: 'course_create', chapter: 1, stepNumber: 4, isSkippable: true, title: 'Criar curso', description: 'Guarde um curso profissional preparado.', actionType: 'SAVE' },
  { id: 'class_create', chapter: 1, stepNumber: 5, isSkippable: true, title: 'Criar turma', description: 'Guarde uma turma com ano curricular e lotação.', actionType: 'SAVE' },
  { id: 'teacher_add', chapter: 1, stepNumber: 6, isSkippable: true, title: 'Adicionar professor', description: 'Adicione um professor ao cenário de demonstração.', actionType: 'SAVE' },
  { id: 'teacher_competency', chapter: 1, stepNumber: 7, isSkippable: true, title: 'Registar competência', description: 'Ligue a competência preparada do professor à disciplina.', actionType: 'SAVE' },
  { id: 'room_add', chapter: 1, stepNumber: 8, isSkippable: true, title: 'Adicionar sala', description: 'Configure uma sala com tipologia e capacidade.', actionType: 'SAVE' },
  { id: 'assignment_create', chapter: 1, stepNumber: 9, isSkippable: true, title: 'Associar disciplina à turma', description: 'Crie uma associação curricular compatível.', actionType: 'SAVE' },
  { id: 'availability_review', chapter: 1, stepNumber: 10, isSkippable: true, title: 'Rever disponibilidade', description: 'A matriz começa com NEUTRAL (1); só IMPOSSIBLE (-1) bloqueia um bloco.', actionType: 'CONFIRM' },
  { id: 'schedule_prepare', chapter: 1, stepNumber: 11, isSkippable: true, title: 'Preparar exemplo', description: 'Prepare um resultado estático no cenário local.', actionType: 'PREPARE' },
  { id: 'schedule_review', chapter: 1, stepNumber: 12, isSkippable: false, title: 'Rever exemplo de horário', description: 'Observe o exemplo preparado sem executar um solver.', actionType: 'CONTINUE' },
  { id: 'schedule_approve', chapter: 1, stepNumber: 13, isSkippable: true, title: 'Aprovar exemplo', description: 'Marque a aprovação simulada do horário de demonstração.', actionType: 'APPROVE' },
  { id: 'chapter_transition', chapter: 1, stepNumber: 14, isSkippable: true, title: 'Resolver a primeira ocorrência', description: 'O primeiro horário está aprovado. Mas amanhã um professor falta e a turma recebe outra disciplina. O que acontece às horas que ficaram por dar?', actionType: 'CONTINUE' },
  { id: 'published_block_open', chapter: 2, stepNumber: 1, isSkippable: false, title: 'Abrir bloco publicado', description: 'Abra um bloco do horário publicado na simulação.', actionType: 'CONTINUE' },
  { id: 'occurrence_create', chapter: 2, stepNumber: 2, isSkippable: true, title: 'Criar ocorrência', description: 'Registe a ocorrência preparada.', actionType: 'SAVE' },
  { id: 'substitute_teacher_select', chapter: 2, stepNumber: 3, isSkippable: true, title: 'Selecionar professor', description: 'Escolha o professor preparado para a substituição.', actionType: 'SELECT' },
  { id: 'substitute_subject_select', chapter: 2, stepNumber: 4, isSkippable: true, title: 'Selecionar disciplina', description: 'Escolha a disciplina preparada para a substituição.', actionType: 'SELECT' },
  { id: 'substitution_complete', chapter: 2, stepNumber: 5, isSkippable: true, title: 'Concluir substituição', description: 'Conclua a execução preparada sem alterar dados reais.', actionType: 'COMPLETE' },
  { id: 'debt_observe', chapter: 2, stepNumber: 6, isSkippable: false, title: 'Observar dívida de horas', description: 'Veja a dívida original preservada no cenário.', actionType: 'CONTINUE' },
  { id: 'repair_simulate', chapter: 2, stepNumber: 7, isSkippable: true, title: 'Simular reparação', description: 'Aplique uma reparação estática no horizonte futuro.', actionType: 'SIMULATE' },
  { id: 'repair_compare', chapter: 2, stepNumber: 8, isSkippable: false, title: 'Comparar reparação', description: 'Compare o cenário antes e depois da reparação.', actionType: 'CONTINUE' },
  { id: 'history_verify', chapter: 2, stepNumber: 9, isSkippable: false, title: 'Confirmar histórico', description: 'Confirme que o histórico de reparação permanece intacto.', actionType: 'CONFIRM' },
  { id: 'repair_approve', chapter: 2, stepNumber: 10, isSkippable: false, title: 'Aprovar reparação', description: 'Conclua o tutorial local sem criar um horário real.', actionType: 'COMPLETE' },
])
