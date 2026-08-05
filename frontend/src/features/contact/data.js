import { useMutation } from '@tanstack/react-query'

const endpoint = import.meta.env.VITE_CONTACT_ENDPOINT || '/api/v1/contact'

async function submitContact(payload) {
  const response = await fetch(endpoint, {
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
  return useMutation({ mutationFn: submitContact })
}
