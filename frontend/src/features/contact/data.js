import { useMutation } from '@tanstack/react-query'

export function getContactEndpoint() {
  const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')
  return `${apiBaseUrl}/contact`
}

async function submitContact(payload) {
  const response = await fetch(getContactEndpoint(), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (response.ok) return
  let data = {}
  try { data = await response.json() } catch { /* Empty or non-JSON error response. */ }
  const error = new Error(data.detail || 'Contact request failed.')
  error.response = { status: response.status, data }
  throw error
}

export function useSubmitContact() {
  return useMutation({ mutationFn: submitContact, retry: false })
}
