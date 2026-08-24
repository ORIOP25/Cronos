/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext } from 'react'
import apiClient from './apiClient'

const ApiClientContext = createContext(apiClient)

export function ApiClientProvider({ client, children }) {
  return <ApiClientContext.Provider value={client || apiClient}>{children}</ApiClientContext.Provider>
}

export function useApiClient() {
  return useContext(ApiClientContext)
}
