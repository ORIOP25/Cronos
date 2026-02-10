// Ficheiro: src/store.js
import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

export const useAuthStore = create(
  persist(
    (set) => ({
      // --- ESTADO ---
      isAuthenticated: false,
      user: null, // Guardará: { email, role, teacherId, orgId }

      // --- AÇÕES ---
      
      // Recebe a resposta completa da API (Token Schema)
      login: (data) => {
        set({ 
          isAuthenticated: true,
          user: {
            email: data.user_email,
            role: data.role,
            teacherId: data.teacher_id,
            orgId: data.organization_id
          }
        })
      },

      logout: () => {
        set({ 
          isAuthenticated: false, 
          user: null 
        })
        localStorage.removeItem('horario-zen-storage')
      },
    }),
    {
      name: 'horario-zen-storage',
      storage: createJSONStorage(() => localStorage),
    }
  )
)