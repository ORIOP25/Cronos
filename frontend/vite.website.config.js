import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  root: 'website',
  publicDir: '../public',
  plugins: [react()],
  define: { 'import.meta.env.VITE_CONTACT_ENDPOINT': JSON.stringify('/api/contact') },
  build: {
    outDir: '../dist-website',
    emptyOutDir: true,
    sourcemap: false,
    manifest: true,
  },
})
