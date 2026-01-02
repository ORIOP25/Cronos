// Ficheiro: src/main.jsx (Frontend)
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'

// Importar o CSS do CoreUI
import '@coreui/coreui/dist/css/coreui.min.css'

// --- 1. IMPORTAR O REACT QUERY ---
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// --- 2. CRIAR O "CLIENTE" QUERY ---
const queryClient = new QueryClient()

// --- 3. RENDERIZAR A APP ---
// Nota: Removemos o RouterProvider daqui porque o App.jsx já tem um Router!
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
)