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
      include: ['src/**/*.{js,jsx}'],
      thresholds: {
        statements: 31,
        branches: 28,
        functions: 24,
        lines: 32,
      },
      exclude: [
        'src/test/**',
        'src/main.jsx',
        'src/assets/**',
      ],
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('@clerk')) return 'vendor-clerk'
          if (id.includes('@coreui')) return 'vendor-coreui'
          if (id.includes('@tanstack') || id.includes('axios')) return 'vendor-data'
          if (id.includes('react')) return 'vendor-react'
          return 'vendor'
        },
      },
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
