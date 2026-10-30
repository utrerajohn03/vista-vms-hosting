import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Dev: the browser talks to Vite, and Vite forwards /api to the FastAPI server.
// Production (Vercel): set VITE_API_URL to the Render URL and the browser calls it directly (CORS).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { '/api': process.env.VITE_PROXY || 'http://127.0.0.1:8000' } },
  test: {
    environment: 'jsdom',
    include: ['e2e/**/*.test.jsx'],
    testTimeout: 30000,
    fileParallelism: false,   // the files share one API and its sign-in rate limit
    env: { VITE_API_URL: process.env.E2E_API || 'http://127.0.0.1:8000' },
  },
});
