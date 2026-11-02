import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// One frontend; local read-only FastAPI proxy or source-validated static JSON.
export default defineConfig({
  plugins: [react()],
  base: '/',
  server: {
    host: '127.0.0.1',
    proxy: {
      '/api': process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:5052',
    },
  },
  build: { outDir: 'dist', sourcemap: false },
});
