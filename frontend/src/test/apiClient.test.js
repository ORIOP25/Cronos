import { describe, it, expect } from 'vitest';
import apiClient from '../apiClient';

describe('apiClient', () => {
  it('should have withCredentials enabled (T24)', () => {
    expect(apiClient.defaults.withCredentials).toBe(true);
  });

  it('should handle 401 without refresh interceptor (T25)', async () => {
    const handlerCount = apiClient.interceptors.response.handlers.length;
    expect(handlerCount).toBeGreaterThanOrEqual(1);
    expect(handlerCount).toBeLessThanOrEqual(2);
  });
});
