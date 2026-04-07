import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In Docker: backend service name is 'backend' on port 8000
// Local dev: use localhost:5000 (FastAPI) or override via env
const API_TARGET = process.env.VITE_API_TARGET || 'http://localhost:5000'

export default defineConfig({
    plugins: [react()],
    server: {
        port: parseInt(process.env.VITE_PORT || '3001'),
        host: '0.0.0.0',
        proxy: {
            '/api': {
                target: API_TARGET,
                changeOrigin: true,
                timeout: 900000,
                proxyTimeout: 900000,
            },
            '/health': {
                target: API_TARGET,
                changeOrigin: true,
            },
        },
    },
})
