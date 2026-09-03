import axios from 'axios';

let getClerkToken = () => Promise.resolve(null);

export const setClerkTokenGetter = (fn) => {
  getClerkToken = fn;
};

function hasAuthorizationHeader(headers) {
  if (!headers) return false;
  if (typeof headers.has === 'function') {
    return headers.has('Authorization') || headers.has('authorization');
  }
  return Object.keys(headers).some((name) => name.toLowerCase() === 'authorization');
}

export function createApiClient({
  adapter,
  authenticate = true,
  baseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1',
} = {}) {
  const client = axios.create({
    baseURL,
    withCredentials: false,
    headers: {
      'Content-Type': 'application/json',
    },
    ...(adapter ? { adapter } : {}),
  });

  if (authenticate) {
    client.interceptors.request.use(async (config) => {
      if (!hasAuthorizationHeader(config.headers)) {
        const token = await getClerkToken();
        if (token) {
          if (config.headers?.set) {
            config.headers.set('Authorization', `Bearer ${token}`);
          } else {
            config.headers = config.headers || {};
            config.headers.Authorization = `Bearer ${token}`;
          }
        }
      }
      return config;
    });
  }

  client.interceptors.response.use(
    (response) => response.data,
    (error) => Promise.reject(error),
  );

  return client;
}

const apiClient = createApiClient();

export default apiClient;
