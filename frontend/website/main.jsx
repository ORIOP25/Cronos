import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import MarketingSite from '../src/pages/MarketingSite.jsx'
import { createQueryClient } from '../src/queryClient.js'
import './website.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <QueryClientProvider client={createQueryClient()}>
      <MarketingSite />
    </QueryClientProvider>
  </React.StrictMode>,
)
