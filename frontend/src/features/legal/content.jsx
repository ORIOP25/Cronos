export const LEGAL_VERSION = '2026-01'
export const LEGAL_EFFECTIVE_DATE = '1 de setembro de 2026'

export const subprocessors = [
  { name: 'Clerk', purpose: 'Conta, autenticação e organizações', location: 'Estados Unidos e regiões suportadas pelo fornecedor' },
  { name: 'Railway', purpose: 'Execução da API, base de dados e workers', location: 'Regiões configuradas na conta Cronos' },
  { name: 'Resend', purpose: 'Entrega de mensagens do formulário de contacto', location: 'Estados Unidos e regiões suportadas pelo fornecedor' },
  { name: 'Cloudflare Turnstile', purpose: 'Prevenção de abuso no formulário de contacto', location: 'Rede global Cloudflare' },
]

export const documents = {
  privacy: {
    title: 'Política de Privacidade',
    intro: 'Esta política explica como o Cronos trata dados pessoais no website e no serviço.',
    sections: [
      ['1. Responsável e contacto', <>O responsável pelo Cronos é Rodrigo Freitas Manguinhas, empresário em nome individual (ENI), NIF 260655350. O contacto é <a href="mailto:contacto@cronos.pt">contacto@cronos.pt</a>. A morada profissional completa deve ser confirmada pelo titular antes da publicação final desta política. Não existe encarregado de proteção de dados designado nesta fase.</>],
      ['2. Papéis no tratamento', <>No contacto comercial, o Cronos trata os dados para responder ao pedido. Nos dados escolares, a escola decide as finalidades e meios. O Cronos atua como subcontratante segundo as instruções da escola.</>],
      ['3. Titulares e categorias de dados', <>Podem ser titulares representantes, professores e membros da organização. O serviço pode conter identificadores profissionais, contactos, horários, disponibilidade e registos operacionais. Não introduza dados de saúde, necessidades educativas ou outros dados sensíveis.</>],
      ['4. Finalidades e fundamentos', <>Usamos os dados para prestar o serviço, proteger contas, responder a contactos e prevenir abuso. Os fundamentos são execução de contrato, diligências pré-contratuais, obrigação legal e interesse legítimo de segurança, conforme aplicável.</>],
      ['5. Fornecedores e destinatários', <>Usamos Clerk, Railway, Resend e Cloudflare Turnstile. Estes fornecedores recebem apenas os dados necessários para cada finalidade. Não vendemos dados nem usamos publicidade comportamental.</>],
      ['6. Transferências internacionais', <>Alguns fornecedores podem tratar dados fora do Espaço Económico Europeu. Aplicamos as salvaguardas contratuais e legais disponibilizadas pelos fornecedores e informamos mudanças materiais.</>],
      ['7. Conservação', <>Conservamos dados escolares enquanto a escola usar o serviço ou até receber instruções. Mantemos evidência de aceitação pelo prazo jurídico necessário. Dados técnicos concluídos são redigidos ou eliminados em prazos mínimos.</>],
      ['8. Direitos', <>Pode pedir acesso, retificação, apagamento, limitação, oposição ou portabilidade. Respondemos, em regra, no prazo legal de um mês. Pedidos sobre dados escolares devem ser dirigidos primeiro à escola.</>],
      ['9. Cookies e armazenamento local', <>Usamos apenas cookies estritamente necessários do Clerk. O Turnstile só é carregado no último passo do contacto. O tutorial e algumas preferências funcionais usam armazenamento local com prazo. Não usamos analytics, publicidade ou perfis comportamentais; por isso não apresentamos um banner de consentimento enquanto esta decisão se mantiver.</>],
      ['10. Segurança', <>Aplicamos autenticação, isolamento por organização, RLS, controlos de acesso, limites de pedidos e logs sem corpos de pedidos. Horários gerados são propostas sujeitas a aprovação humana; não há decisões exclusivamente automatizadas.</>],
      ['11. Alterações', <>Esta é a versão 2026-01, vigente desde 1 de setembro de 2026. Publicaremos alterações materiais com a nova versão. A nova versão pode exigir nova aceitação da organização.</>],
      ['12. Reclamações', <>Pode apresentar reclamação à Comissão Nacional de Proteção de Dados (CNPD), sem prejuízo de outros direitos.</>],
    ],
  },
  terms: {
    title: 'Termos de Serviço',
    intro: 'Estes termos regulam o uso do Cronos por organizações profissionais.',
    sections: [
      ['1. Serviço e autoridade', <>O Cronos é um serviço para organizações profissionais. A pessoa que aceita deve ter poderes para vincular a organização.</>],
      ['2. Conta e uso permitido', <>Mantenha as credenciais seguras. Use o serviço apenas para gerir a atividade escolar autorizada. É proibido abusar do serviço, contornar controlos ou introduzir conteúdo ilícito.</>],
      ['3. Dados do cliente', <>Não introduza dados excessivos ou sensíveis. A escola mantém a responsabilidade pelos dados que escolhe introduzir e pelas instruções dadas ao Cronos.</>],
      ['4. Horários e revisão humana', <>O gerador produz propostas. Um responsável deve rever e aprovar cada horário. Não garantimos um resultado perfeito ou adequado sem revisão.</>],
      ['5. Propriedade e confidencialidade', <>O Cronos mantém os direitos sobre o software. A escola mantém os direitos sobre os seus dados e concede licença limitada para prestar o serviço. As partes protegem informação confidencial.</>],
      ['6. Fornecedores e segurança', <>Podemos usar fornecedores técnicos indicados na Política de Privacidade e no DPA. Podemos suspender o acesso por abuso, risco de segurança ou obrigação legal.</>],
      ['7. Cessação', <>Na cessação, a escola pode pedir exportação. Eliminamos os dados operacionais segundo as instruções e preservamos apenas o que a lei exigir.</>],
      ['8. Preço e responsabilidade', <>A fase gratuita atual não cria uma obrigação de cobrança. Antes de cobrar, publicaremos condições comerciais revistas. A responsabilidade limita-se aos montantes pagos nos 12 meses anteriores, salvo exclusões impostas por normas imperativas.</>],
      ['9. Lei e alterações', <>Aplicam-se a lei portuguesa e os tribunais competentes determinados pelas normas imperativas aplicáveis. Alterações materiais podem exigir nova aceitação.</>],
    ],
  },
  dpa: {
    title: 'Acordo de Tratamento de Dados',
    intro: 'Este DPA aplica-se quando a escola usa o Cronos para dados escolares. A escola é identificada pelos dados fornecidos na aceitação e as partes devem completar os contactos de negócio aplicáveis antes da contratação.',
    sections: [
      ['1. Partes e objeto', <>A escola identificada no formulário é o responsável e o operador do Cronos é o subcontratante. O objeto é prestar gestão de horários, faltas, substituições e configuração escolar.</>],
      ['2. Duração, natureza e finalidade', <>O tratamento dura durante o serviço. Inclui recolha, armazenamento, consulta, organização, exportação e eliminação, apenas para as finalidades documentadas pela escola.</>],
      ['3. Dados e titulares', <>Os dados podem incluir identificadores profissionais, contactos, horários, disponibilidade, ocorrências e notas operacionais. As categorias podem incluir trabalhadores, membros e representantes da escola.</>],
      ['4. Instruções e confidencialidade', <>O Cronos trata dados apenas segundo instruções documentadas. Pessoas autorizadas ficam sujeitas a confidencialidade.</>],
      ['5. Medidas técnicas e organizativas', <>Aplicamos medidas técnicas e organizativas proporcionais, incluindo autenticação, isolamento de tenants, RLS, controlo de acesso, minimização de logs, recuperação operacional e gestão de incidentes. O Anexo B deve ser lido com a configuração efetiva do serviço.</>],
      ['6. Direitos, DPIA e auditoria', <>Apoiamos pedidos de acesso, retificação, apagamento, limitação, oposição e portabilidade, avaliações de impacto e contactos com autoridades. Fornecemos evidências razoáveis e permitimos auditorias proporcionais, sem prejudicar a segurança ou a confidencialidade de outros clientes.</>],
      ['7. Violações', <>Notificaremos a escola sem demora injustificada após confirmar uma violação de dados pessoais e forneceremos a informação disponível para avaliação, contenção e comunicação às autoridades ou titulares.</>],
      ['8. Subcontratantes', <>A escola autoriza os subprocessadores listados no Anexo A. Avisaremos com 14 dias de antecedência sobre alterações. A escola pode apresentar objeção fundamentada e o Cronos continua responsável pelos subprocessadores nos limites legais.</>],
      ['9. Transferências internacionais', <>As transferências internacionais usam mecanismos legais aplicáveis, incluindo decisões de adequação ou cláusulas contratuais-tipo (SCC) quando necessário. O Anexo C identifica o mecanismo relevante, a finalidade e as medidas suplementares aplicáveis.</>],
      ['10. Fim do serviço', <>No fim, devolvemos ou eliminamos dados operacionais segundo a instrução da escola, salvo retenção legal. A evidência contratual pode ser preservada pelo prazo necessário.</>],
      ['11. Anexos', <>Anexo A — subprocessadores; Anexo B — medidas técnicas e organizativas; Anexo C — transferências e SCC; Anexo D — instruções documentadas, categorias, prazos e contactos. Estes anexos fazem parte do DPA e devem ser atualizados quando a configuração material mudar.</>],
    ],
  },
  cookies: {
    title: 'Cookies e armazenamento local',
    intro: 'O Cronos mantém uma superfície simples e sem tracking opcional.',
    sections: [
      ['Cookies estritamente necessários', <>O Clerk pode usar cookies necessários para autenticação e sessão.</>],
      ['Turnstile', <>O Cloudflare Turnstile só é carregado no último passo do formulário de contacto para prevenir abuso.</>],
      ['Armazenamento funcional', <>Guardamos localmente o progresso do tutorial e preferências funcionais com prazo limitado. Não usamos estes dados para criar perfis.</>],
      ['Sem tracking opcional', <>Não usamos analytics, publicidade, pixels ou perfis comportamentais. Reavaliaremos esta decisão antes de adicionar qualquer tracking opcional.</>],
    ],
  },
}
