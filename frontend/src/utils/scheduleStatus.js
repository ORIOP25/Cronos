export const TERMINAL_STATUSES = ['SUCCESS', 'FAILURE', 'Success', 'Error', 'Impossible', 'REVOKED', 'CANCELED']

export function isPending(status) {
  return !!status && !TERMINAL_STATUSES.some(s => status.includes(s))
}
