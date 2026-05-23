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
    // token not ready, fall back to cookie (withCredentials)
  }
  return config;
});



apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status;
    if (status === 404) {
      return Promise.resolve(error.response);
    }
    if (status === 403) {
      const detail = error?.response?.data?.detail;
      if (detail && !window._403_toast_shown) {
        window._403_toast_shown = true;
        setTimeout(() => { window._403_toast_shown = false }, 3000);
      }
    }
    return Promise.reject(error);
  }
);



export default apiClient;
