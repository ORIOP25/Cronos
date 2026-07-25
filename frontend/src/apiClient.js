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
  const token = await getClerkToken();
  // A caller may provide a freshly minted organization-scoped token. Never
  // replace it with the application-wide token getter's current value.
  if (token && !config.headers.Authorization) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response.data,
  (error) => Promise.reject(error),
);

export default apiClient;
