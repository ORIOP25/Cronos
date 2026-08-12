export const BRAND_TAGLINE_LOGIN =
  'O software de gestão pensado para o Ensino Profissional. Horários dinâmicos, progresso curricular visível e substituições em 1 minuto.'

export const BRAND_TAGLINE_REGISTER =
  'Junte-se às escolas profissionais que já simplificaram a gestão de horários. Comece em minutos, sem complicações.'

export const BRAND_TAGLINE_CREATEORG =
  'Dê um nome à sua organização. É o primeiro passo para ter uma visão completa da sua escola num só lugar.'

export const BRAND_STATS_LOGIN = [
  { value: '< 30 min', label: 'Gerar horário' },
  { value: '0', label: 'Horas perdidas' },
  { value: '100%', label: 'Auditável' },
]

export const BRAND_STATS_REGISTER = [
  { value: '3 passos', label: 'Começar' },
  { value: 'Ilimitados', label: 'Utilizadores' },
  { value: '24/7', label: 'Disponível' },
]

export const BRAND_STATS_CREATEORG = [
  { value: 'Passo 2', label: 'de 3' },
  { value: '1 min', label: 'Configurar' },
  { value: 'Pronto', label: 'a usar' },
]

export const CLERK_LOCALIZATION_PT = {
  socialButtonsBlockButton: 'Continuar com {{provider}}',
  formFieldLabel__emailAddress: 'Email',
  formFieldLabel__password: 'Palavra-passe',
  formFieldLabel__firstName: 'Nome',
  formFieldLabel__lastName: 'Apelido',
  formFieldInputPlaceholder__emailAddress: 'nome@escola.pt',
  formFieldInputPlaceholder__password: 'A sua palavra-passe',
  formButtonPrimary: 'Continuar',
  footerActionLink__signIn: 'Já tem conta? Entrar',
  footerActionLink__signUp: 'Não tem conta? Registar',
  dividerText: 'ou',
}

export const CLERK_APPEARANCE_AUTH = {
  layout: {
    socialButtonsPlacement: 'bottom',
    socialButtonsVariant: 'iconButton',
  },
  variables: {
    colorPrimary: '#5c3d2e',
    colorBackground: '#ffffff',
    colorText: '#1a1512',
    colorTextSecondary: '#8b6f5c',
    colorInputBackground: '#faf8f5',
    colorInputText: '#1a1512',
    colorInputBorder: '#e0d6cc',
    colorShimmer: '#f5f0eb',
    fontFamily: '"Outfit", sans-serif',
    fontFamilyButtons: '"Outfit", sans-serif',
    fontSize: '15px',
    borderRadius: '4px',
  },
  elements: {
    card: {
      boxShadow: 'none',
      border: 'none',
      width: '100%',
      background: 'transparent',
    },
    formButtonPrimary: {
      backgroundColor: '#5c3d2e',
      fontSize: '0.82rem',
      fontWeight: '600',
      textTransform: 'uppercase',
      letterSpacing: '0.12em',
      padding: '14px 28px',
      border: 'none',
      borderRadius: '4px',
      '&:hover': { backgroundColor: '#4a2e1e', transform: 'translateY(-1px)' },
    },
    formFieldInput: {
      padding: '14px 16px',
      fontSize: '0.94rem',
      border: '1px solid #e0d6cc',
      borderRadius: '4px',
      backgroundColor: '#faf8f5',
      '&:focus': { borderColor: '#d4940b', boxShadow: '0 0 0 3px rgba(212, 148, 11, 0.1)' },
    },
    formFieldLabel: {
      fontSize: '0.72rem',
      fontWeight: '600',
      textTransform: 'uppercase',
      letterSpacing: '0.08em',
      color: '#5c3d2e',
    },
    headerTitle: {
      fontFamily: '"Playfair Display", serif',
      fontSize: '1.6rem',
      fontWeight: '700',
      color: '#3d2b1f',
    },
    headerSubtitle: {
      fontSize: '0.92rem',
      color: '#8b6f5c',
    },
    footerActionText: {
      color: '#8b6f5c',
      fontSize: '0.88rem',
    },
    footerActionLink: {
      color: '#d4940b',
      fontWeight: '600',
      textDecoration: 'none',
      '&:hover': { color: '#5c3d2e' },
    },
    dividerRow: {
      margin: '28px 0',
    },
    dividerText: {
      color: '#8b6f5c',
      opacity: 0.5,
      fontSize: '0.72rem',
      textTransform: 'uppercase',
      letterSpacing: '0.08em',
    },
    socialButtonsBlockButton: {
      border: '1px solid #e0d6cc',
      borderRadius: '4px',
      '&:hover': { backgroundColor: '#faf8f5', borderColor: '#5c3d2e' },
    },
    identityPreview: {
      fontFamily: '"Outfit", sans-serif',
    },
    otpCodeFieldInput: {
      border: '1px solid #e0d6cc',
      borderRadius: '4px',
      fontFamily: '"Outfit", sans-serif',
    },
    alert: {
      borderRadius: '4px',
      fontFamily: '"Outfit", sans-serif',
    },
  },
}
