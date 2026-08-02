import { useMutation } from '@tanstack/react-query'
import apiClient from '../../apiClient'

export function useSubmitContact() {
  return useMutation({ mutationFn: (payload) => apiClient.post('/contact', payload) })
}
