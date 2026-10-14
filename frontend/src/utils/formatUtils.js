/**
 * Utilitários centralizados de formatação para o Cronos.
 * Todas as datas e números devem passar por estas funções para garantir consistência.
 */

/**
 * Formata uma data ISO para DD/MM/AAAA (ex: "05/04/2026").
 * @param {string|null} dateStr - Data no formato YYYY-MM-DD
 * @returns {string} Data formatada ou "—"
 */
export function formatDate(dateStr) {
  if (!dateStr) return '—'
  const d = new Date(`${dateStr}T12:00:00`)
  if (Number.isNaN(d.getTime())) return dateStr
  return d.toLocaleDateString('pt-PT', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
}

/**
 * Formata uma data ISO para o valor apresentado nos campos de data.
 * @param {string|null} dateStr - Data no formato YYYY-MM-DD
 * @returns {string} Data no formato DD/MM/AAAA ou ""
 */
export function formatDateInput(dateStr) {
  if (!dateStr) return ''
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateStr)
  if (!match) return dateStr
  const [, year, month, day] = match
  return `${day}/${month}/${year}`
}

/**
 * Converte uma data introduzida pelo utilizador para ISO.
 * Aceita DD/MM/AAAA e YYYY-MM-DD para facilitar colagens e testes existentes.
 * @param {string|null} value
 * @returns {string|null} Data ISO, "" para vazio ou null para valor inválido
 */
export function parseDateInput(value) {
  const text = String(value ?? '').trim()
  if (!text) return ''

  let year
  let month
  let day
  const displayMatch = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(text)
  const isoMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text)
  if (displayMatch) {
    [, day, month, year] = displayMatch
  } else if (isoMatch) {
    [, year, month, day] = isoMatch
  } else {
    return null
  }

  const date = new Date(Number(year), Number(month) - 1, Number(day), 12)
  if (
    date.getFullYear() !== Number(year)
    || date.getMonth() !== Number(month) - 1
    || date.getDate() !== Number(day)
  ) {
    return null
  }
  return `${year}-${month}-${day}`
}

/**
 * Formata uma data ISO para "04 Abr" (dia + mês abreviado, sem ano).
 * @param {string|null} dateStr - Data no formato YYYY-MM-DD
 * @returns {string} Data formatada ou ""
 */
export function formatDateShort(dateStr) {
  if (!dateStr) return ''
  const d = new Date(`${dateStr}T12:00:00`)
  if (Number.isNaN(d.getTime())) return dateStr
  return d.toLocaleDateString('pt-PT', {
    day: '2-digit',
    month: 'short',
  })
}

/**
 * Formata uma data ISO para "04 de Abril de 2026".
 * @param {string|null} dateStr - Data no formato YYYY-MM-DD
 * @returns {string} Data formatada ou "—"
 */
export function formatDateLong(dateStr) {
  if (!dateStr) return '—'
  const d = new Date(`${dateStr}T12:00:00`)
  if (Number.isNaN(d.getTime())) return dateStr
  return d.toLocaleDateString('pt-PT', {
    day: '2-digit',
    month: 'long',
    year: 'numeric',
  })
}

/**
 * Formata um timestamp ISO completo para data e hora (ex: "05/04/2026, 14:30").
 * @param {string|null} dateTimeStr
 * @returns {string}
 */
export function formatDateTime(dateTimeStr) {
  if (!dateTimeStr) return '—'
  const d = new Date(dateTimeStr)
  if (Number.isNaN(d.getTime())) return dateTimeStr
  return d.toLocaleString('pt-PT', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/**
 * Calcula a segunda-feira de uma semana a partir de qualquer data.
 * @param {Date} dateValue
 * @returns {string} Data ISO (YYYY-MM-DD)
 */
export function toWeekMonday(dateValue) {
  const d = toLocalDate(dateValue)
  if (!d) return ''
  const dayOfWeek = d.getDay()
  const offset = dayOfWeek === 0 ? -6 : 1 - dayOfWeek
  d.setDate(d.getDate() + offset)
  return toIsoDate(d)
}

/**
 * Converte um Date para string ISO (YYYY-MM-DD).
 * @param {Date} dateValue
 * @returns {string}
 */
export function toIsoDate(dateValue) {
  if (!(dateValue instanceof Date) || Number.isNaN(dateValue.getTime())) return ''
  const year = dateValue.getFullYear()
  const month = String(dateValue.getMonth() + 1).padStart(2, '0')
  const day = String(dateValue.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

/**
 * Segunda-feira da semana atual.
 * @returns {string} Data ISO
 */
export function getCurrentWeekMonday() {
  return toWeekMonday(new Date())
}

/**
 * Adiciona (ou subtrai) dias a uma data ISO.
 * @param {string} dateStr - YYYY-MM-DD
 * @param {number} days
 * @returns {string} YYYY-MM-DD
 */
export function addDays(dateStr, days) {
  const d = toLocalDate(dateStr)
  if (!d || !Number.isFinite(days)) return ''
  d.setDate(d.getDate() + days)
  return toIsoDate(d)
}

function toLocalDate(dateValue) {
  if (dateValue instanceof Date) {
    if (Number.isNaN(dateValue.getTime())) return null
    return new Date(dateValue.getFullYear(), dateValue.getMonth(), dateValue.getDate(), 12)
  }
  if (typeof dateValue !== 'string') return null
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateValue)
  if (!match) return null
  const [, year, month, day] = match.map(Number)
  const date = new Date(year, month - 1, day, 12)
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) return null
  return date
}

/**
 * Formata um intervalo semanal (ex: "04 Abr – 08 Abr 2026").
 * @param {string} weekStart - YYYY-MM-DD (segunda-feira)
 * @returns {string}
 */
export function formatWeekRange(weekStart) {
  const start = new Date(`${weekStart}T12:00:00`)
  const end = new Date(`${weekStart}T12:00:00`)
  end.setDate(end.getDate() + 4)
  const short = { day: '2-digit', month: 'short' }
  const full = { day: '2-digit', month: 'short', year: 'numeric' }
  return `${start.toLocaleDateString('pt-PT', short)} – ${end.toLocaleDateString('pt-PT', full)}`
}

/**
 * Normaliza hora para HH:MM.
 * @param {string} value
 * @returns {string}
 */
export function normalizeTimeLabel(value) {
  if (!value) return ''
  const text = String(value)
  if (text.length >= 5) return text.slice(0, 5)
  return text
}

/**
 * Formata um intervalo de horas como "HH:MM–HH:MM"; vazio se faltar uma das pontas.
 */
export function formatTimeRange(start, end) {
  return start && end ? `${normalizeTimeLabel(start)}–${normalizeTimeLabel(end)}` : ''
}

/**
 * Formata minutos como duração legível em português: "50 min" ou "1 h 40 min".
 * @param {number|null} minutes
 * @returns {string}
 */
export function formatDurationMinutes(minutes) {
  const total = Math.round(Number(minutes) || 0)
  if (total <= 0) return '0 min'
  if (total < 60) return `${total} min`
  const hours = Math.floor(total / 60)
  const rest = total % 60
  return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`
}

/**
 * Formata horas decimais do backend como duração legível.
 * @param {number|null} hours
 * @returns {string}
 */
export function formatDurationHours(hours) {
  return formatDurationMinutes((Number(hours) || 0) * 60)
}

/**
 * Verifica se uma data é posterior a outra (comparação apenas por dia).
 * @param {string} leftDate - YYYY-MM-DD
 * @param {string} rightDate - YYYY-MM-DD
 * @returns {boolean}
 */
export function isAfterDate(leftDate, rightDate) {
  return new Date(`${leftDate}T12:00:00`) > new Date(`${rightDate}T12:00:00`)
}
