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

export function getApiErrorMessage(error, fallbackMessage = TXT.ERROR_UNKNOWN) {
  const detail = error?.response?.data?.detail

  const message = clean(detail)
    || (Array.isArray(detail) ? fromArrayDetail(detail) : null)
    || fromObjectDetail(detail)
    || clean(error?.message)
    || fallbackMessage

  return humanizeOperationalDetail(message)
}
