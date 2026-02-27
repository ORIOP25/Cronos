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
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

// ==========================================
// INTERCEPTORS (Interceptadores de Pedidos)
// ==========================================

let refreshPromise = null;

// 1. Interceptor de RESPONSE: Gere Sessão Expirada (Erro 401)
apiClient.interceptors.response.use(
  (response) => response, // Se correu bem, passa à frente
  async (error) => {
    const originalRequest = error.config || {};
    const isAuthRefresh = originalRequest.url?.includes('/auth/refresh');

    // Se recebermos um 401 (Unauthorized), tentamos refresh uma vez
    if (error.response && error.response.status === 401 && !originalRequest._retry && !isAuthRefresh) {
      originalRequest._retry = true;
      try {
        if (!refreshPromise) {
          refreshPromise = apiClient.post('/auth/refresh');
        }
        await refreshPromise;
        refreshPromise = null;
        return apiClient(originalRequest);
      } catch (refreshError) {
        refreshPromise = null;
        console.warn('⚠️ Sessão expirada ou inválida. A fazer logout...');
        useAuthStore.getState().logout();
        localStorage.clear();
        if (window.location.pathname !== '/login') {
          window.location.href = '/login';
        }
        return refreshError;
      }
    }

    return error;
  }
);

// --- API HELPER FUNCTIONS (Novas) ---
export const auth = {
  login: (credentials) => {
    const formData = new URLSearchParams();
    formData.append('username', credentials.email);
    formData.append('password', credentials.password);
    return apiClient.post('/auth/token', formData, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
    });
  },
  logout: () => apiClient.post('/auth/logout')
};

export const teachers = {
  getAll: () => apiClient.get('/teachers/'),
  create: (data) => apiClient.post('/teachers/', data),
  // delete: (id) => apiClient.delete(`/teachers/${id}`), // Futuro
};

export default apiClient;