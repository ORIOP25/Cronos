// Ficheiro: src/main.jsx (Frontend)
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'

// Importar o CSS do CoreUI
import '@coreui/coreui/dist/css/coreui.min.css'

// Importar o Router
import { createBrowserRouter, RouterProvider } from 'react-router-dom'

// --- 1. IMPORTAR O REACT QUERY ---
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// Importar as nossas páginas
import Login from './pages/Login.jsx'
import ProtectedRoute from './components/ProtectedRoute.jsx'
import DefaultLayout from './components/DefaultLayout.jsx'
import ImportProfessores from './pages/ImportProfessores.jsx'
import Dashboard from './pages/Dashboard.jsx'
import MyAvailability from './pages/MyAvailability.jsx'

// --- 2. CRIAR O "CLIENTE" QUERY ---
// Esta é a instância principal do nosso gestor de API
const queryClient = new QueryClient()

// --- 2. DEFINIR AS NOSSAS ROTAS (ATUALIZADO) ---
const router = createBrowserRouter([
  {
    path: "/",
    element: <App />, 
    children: [
      {
        path: "login",
        element: <Login />,
      },
      {
        // 3. ROTA "PAI" PROTEGIDA
        // Esta rota usa o "Guarda-Costas"
        // E define o "Layout" principal
        path: "/", // Corresponde à raiz
        element: (
          <ProtectedRoute>
            <DefaultLayout />
          </ProtectedRoute>
        ),
        // 4. "FILHOS" DO LAYOUT
        // Estas páginas vão aparecer dentro do <Outlet> do DefaultLayout
        children: [
          {
            path: "dashboard",
            element: <Dashboard />, // <--- AQUI
          },
          {
            path: "import", // Mostra em /import
            element: <ImportProfessores />
          },
          {
          path: "my-availability",
          element: <MyAvailability />
          }
        ]
      },
    ],
  },
]);

// --- 4. "EMBRULHAR" A APP COM OS PROVIDERS ---
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {/* O React Query tem de "embrulhar" o Router */}
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </React.StrictMode>,
)