import axios from 'axios';

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

let getClerkToken = null;

export const setClerkTokenGetter = (fn) => {
  getClerkToken = fn;
};

apiClient.interceptors.request.use(async (config) => {
  if (getClerkToken) {
    try {
      const token = await getClerkToken();
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    } catch {
      // token not ready yet, fall back to cookie
    }
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401 && !window.location.pathname.startsWith('/login')) {
      window.location.href = '/login'
    }
    return Promise.reject(error);
  }
);

export const teachers = {
  getAll: () => apiClient.get('/teachers/'),
  create: (data) => apiClient.post('/teachers/', data),
};

export default apiClient;
