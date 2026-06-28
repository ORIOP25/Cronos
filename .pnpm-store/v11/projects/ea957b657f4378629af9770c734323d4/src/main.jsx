import React from 'react'
import ReactDOM from 'react-dom/client'
import { ClerkProvider } from '@clerk/react'
import App from './App.jsx'
import ErrorBoundary from './components/ErrorBoundary'
import { ToastProvider } from './contexts/ToastContext'

import '@coreui/coreui/dist/css/coreui.min.css'
import './index.css'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const queryClient = new QueryClient()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ErrorBoundary>
      <ToastProvider>
        <QueryClientProvider client={queryClient}>
          <ClerkProvider publishableKey={import.meta.env.VITE_CLERK_PUBLISHABLE_KEY} afterSignOutUrl="/" localization={{ socialButtonsBlockButton: 'Continuar com {{provider}}', formFieldLabel__emailAddress: 'Email', formFieldLabel__password: 'Palavra-passe', formButtonPrimary: 'Entrar', footerActionLink__signIn: 'Já tem conta? Entrar', footerActionLink__signUp: 'Não tem conta? Registar' }}>
            <App />
          </ClerkProvider>
        </QueryClientProvider>
      </ToastProvider>
    </ErrorBoundary>
  </React.StrictMode>,
)
