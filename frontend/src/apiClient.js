import axios from 'axios';

let getClerkToken = () => Promise.resolve(null);

export const setClerkTokenGetter = (fn) => {
  getClerkToken = fn;
};

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
      const token = await getClerkToken();
      // A caller may provide a freshly minted organization-scoped token. Never
      // replace it with the application-wide token getter's current value.
      if (token && !config.headers.Authorization) {
        config.headers.Authorization = `Bearer ${token}`;
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
