import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
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
