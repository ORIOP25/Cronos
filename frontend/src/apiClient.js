// Ficheiro: src/apiClient.js

import axios from 'axios';
import { useAuthStore } from './store';

// ==========================================
// CONFIGURAÇÃO DO CLIENTE API
// ==========================================

const apiClient = axios.create({
  // MUDANÇA CRÍTICA: Usamos caminho relativo.
  // O Nginx vai receber este pedido e encaminhar para o container do backend.
  baseURL: '/api/v1', 
  headers: {
    'Content-Type': 'application/json',
  },
});

// ==========================================
// INTERCEPTORS (Interceptadores de Pedidos)
// ==========================================

// 1. Interceptor de REQUEST: Anexa o Token automaticamente
apiClient.interceptors.request.use(
  (config) => {
    // Vamos buscar o token à store do Zustand
    const accessToken = useAuthStore.getState().accessToken;
    
    if (accessToken) {
      config.headers.Authorization = `Bearer ${accessToken}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// 2. Interceptor de RESPONSE: Gere Sessão Expirada (Erro 401)
apiClient.interceptors.response.use(
  (response) => response, // Se correu bem, passa à frente
  (error) => {
    // Se recebermos um 401 (Unauthorized), significa que o token morreu
    if (error.response && error.response.status === 401) {
      console.warn('⚠️ Sessão expirada ou inválida. A fazer logout...');
      
      // Ação 1: Limpar o estado local (Logout)
      useAuthStore.getState().logout();
      
      // Ação 2: Redirecionar para o Login
      // Nota: Verificamos se já não estamos no login para evitar loops
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export default apiClient;