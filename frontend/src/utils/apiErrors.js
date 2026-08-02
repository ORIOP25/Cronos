import { TXT, humanizeOperationalDetail } from './terminology'

const clean = (value) => (typeof value === 'string' && value.trim() ? value.trim() : null)

const fromArrayDetail = (detail) => {
  const messages = detail
    .map((item) => {
      if (typeof item === 'string') return item
      if (item && typeof item === 'object') {
        return item.msg || item.message || item.detail || ''
      }
      return ''
    })
    .map(clean)
    .filter(Boolean)

  return messages.length > 0 ? messages.join(' ') : null
}

const fromObjectDetail = (detail) => {
  if (!detail || typeof detail !== 'object') return null
  return clean(detail.message) || clean(detail.msg) || clean(detail.detail)
}

const statusMessage = (status) => {
  if (status === 401) return 'A sua sessão terminou. Entre novamente.'
  if (status === 403) return 'Não tem permissão para realizar esta ação.'
  if (status === 429) return 'Foram efetuadas v?rias tentativas. Aguarde e tente novamente.'
  if (status >= 500) return 'O servidor encontrou um problema. Tente novamente dentro de instantes.'
  return null
}

export function getApiErrorMessage(error, fallbackMessage = TXT.ERROR_UNKNOWN) {
  const detail = error?.response?.data?.detail
  const isNetworkError = error?.code === 'ERR_NETWORK'
    || (!error?.response && clean(error?.message)?.toLowerCase() === 'network error')

  const message = clean(detail)
    || (Array.isArray(detail) ? fromArrayDetail(detail) : null)
    || fromObjectDetail(detail)
    || (isNetworkError
      ? 'Não foi possível ligar ao servidor. Verifique a ligação e tente novamente.'
      : null)
    || statusMessage(error?.response?.status)
    || fallbackMessage

  return humanizeOperationalDetail(message)
}
