import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backendTarget = process.env.VITE_API_TARGET || 'http://127.0.0.1:8001'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/auth': backendTarget,
      '/lsta': backendTarget,
      '/lda': backendTarget,
      '/lma': backendTarget,
      '/laa': backendTarget,
      '/admin': backendTarget,
    },
  },
})
