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
  if (Number.isNaN(d)) return dateStr
  return d.toLocaleDateString('pt-PT', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
}

/**
 * Formata uma data ISO para "04 Abr" (dia + mês abreviado, sem ano).
 * @param {string|null} dateStr - Data no formato YYYY-MM-DD
 * @returns {string} Data formatada ou ""
 */
export function formatDateShort(dateStr) {
  if (!dateStr) return ''
  const d = new Date(`${dateStr}T12:00:00`)
  if (Number.isNaN(d)) return dateStr
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
  if (Number.isNaN(d)) return dateStr
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
  if (Number.isNaN(d)) return dateTimeStr
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
  const d = new Date(dateValue)
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
  const today = new Date()
  const dayOfWeek = today.getDay()
  const diff = dayOfWeek === 0 ? -6 : 1 - dayOfWeek
  const monday = new Date(today + diff * 24 * 60 * 60 * 1000)
  return monday.toISOString().split('T')[0]
}

/**
 * Adiciona (ou subtrai) dias a uma data ISO.
 * @param {string} dateStr - YYYY-MM-DD
 * @param {number} days
 * @returns {string} YYYY-MM-DD
 */
export function addDays(dateStr, days) {
  const d = new Date(`${dateStr}T12:00:00`)
  d.setDate(d.getDate() + days)
  return d.toISOString().split('T')[0]
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
 * Formata um número com separador de milhares PT-PT (ex: 1 200).
 * @param {number} value
 * @returns {string}
 */
export function formatNumber(value) {
  return Number(value).toLocaleString('pt-PT')
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
 * Verifica se uma data é posterior a outra (comparação apenas por dia).
 * @param {string} leftDate - YYYY-MM-DD
 * @param {string} rightDate - YYYY-MM-DD
 * @returns {boolean}
 */
export function isAfterDate(leftDate, rightDate) {
  return new Date(`${leftDate}T12:00:00`) > new Date(`${rightDate}T12:00:00`)
}
