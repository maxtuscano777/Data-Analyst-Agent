import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    tailwindcss(),
    react(),
  ],
  server: {
    port: 5173,
    proxy: {
      // Proxy API and WebSocket calls to the FastAPI backend in development
      '/ws': { target: 'ws://localhost:8000', ws: true },
      '/upload': { target: 'http://localhost:8000' },
      '/health': { target: 'http://localhost:8000' },
    },
  },
})
