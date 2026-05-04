import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.js',
    css: false,
    exclude: ['e2e/**', 'node_modules/**'],
    coverage: {
      provider: 'v8',
      reporter: ['lcov', 'text'],
      reportsDirectory: './coverage',
      exclude: [
        'src/test/**',
        'src/main.jsx',
        'src/assets/**',
      ],
    },
  },
  server: {
    host: true, // Permite que o Docker aceda (0.0.0.0)
    port: 5173, // Porta padrão do Vite
    watch: {
      usePolling: true, // Força o Windows a detetar mudanças de ficheiros
    },
    proxy: {
      // Quando o frontend pede "/api/...", o Vite manda para o Backend
      '/api': {
        target: 'http://backend:8000',
        changeOrigin: true,
      }
    }
  }
})