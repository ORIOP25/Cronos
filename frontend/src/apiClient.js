import axios from 'axios';

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

let getClerkToken = () => Promise.resolve(null);

export const setClerkTokenGetter = (fn) => {
  getClerkToken = fn;
};

apiClient.interceptors.request.use(async (config) => {
  try {
    const token = await getClerkToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  } catch {
    // Token retrieval failed; protected endpoints will reject the unauthenticated request.
  }
  return config;
});

export default apiClient;
