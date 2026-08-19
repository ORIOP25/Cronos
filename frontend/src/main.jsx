import React from 'react'
import ReactDOM from 'react-dom/client'
import { ClerkProvider } from '@clerk/react'
import App from './App.jsx'
import ErrorBoundary from './components/ErrorBoundary'
import { UserQueryProvider } from './UserQueryProvider'
import { CLERK_LOCALIZATION_PT } from './utils/authDesign'

import '@coreui/coreui/dist/css/coreui.min.css'
import './index.css'
import './styles/brand.tokens.css'
import './styles/app-shell.css'
import './styles/app-components.css'
import './styles/guided-form.css'
import './styles/week-grid.css'
import './styles/availability-grid.css'
import './styles/availability-toolbar.css'
import './styles/dashboard.css'
import './styles/smart-table.css'
import './styles/modal.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ClerkProvider
      publishableKey={import.meta.env.VITE_CLERK_PUBLISHABLE_KEY}
      afterSignOutUrl="/"
      localization={CLERK_LOCALIZATION_PT}
    >
      <ErrorBoundary>
        <UserQueryProvider>
          <App />
        </UserQueryProvider>
      </ErrorBoundary>
    </ClerkProvider>
  </React.StrictMode>,
)
