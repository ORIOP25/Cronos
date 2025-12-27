// Ficheiro: src/store.js

import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

export const useAuthStore = create(
  persist(
    (set) => ({
      // --- ESTADO (DADOS) ---
      accessToken: null,
      role: null,
      isAuthenticated: false,
      userEmail: null, // Útil para mostrar "Olá, user@email.com" na navbar

      // --- AÇÕES (FUNÇÕES) ---
      
      // 1. Ação de Login (Chamada pelo Login.jsx)
      // Nota: O Login.jsx envia (token, role). Adicionei email como opcional.
      setLogin: (token, role, email = null) => {
        set({ 
          accessToken: token, 
          role: role, 
          userEmail: email,
          isAuthenticated: true 
        })
      },

      // 2. Ação de Logout
      logout: () => {
        set({ 
          accessToken: null, 
          role: null, 
          userEmail: null,
          isAuthenticated: false 
        })
        
        // Limpeza extra de segurança
        localStorage.removeItem('horario-zen-storage')
        
        // Redirecionar se não estivermos já no login
        if (window.location.pathname !== '/login') {
          window.location.href = '/login'
        }
      },
    }),
    {
      // Nome da chave no browser (podes ver isto na Tab Application > Local Storage)
      name: 'horario-zen-storage', 
      storage: createJSONStorage(() => localStorage),
    }
  )
)