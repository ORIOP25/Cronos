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
    exclude: ['e2e/**', 'scripts/**', 'node_modules/**'],
    coverage: {
      provider: 'v8',
      reporter: ['lcov', 'text'],
      reportsDirectory: './coverage',
      include: ['src/**/*.{js,jsx}'],
      thresholds: {
        statements: 45,
        branches: 40,
        functions: 35,
        lines: 45,
      },
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
    proxy: {
      // Quando o frontend pede "/api/...", o Vite manda para o Backend
      '/api': {
        target: 'http://backend:8000',
        changeOrigin: true,
      }
    }
  }
})
