import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// One frontend; local read-only FastAPI proxy or source-validated static JSON.
export default defineConfig({
  plugins: [react()],
  base: process.env.GITHUB_PAGES === '1' ? '/finance_dashboard/' : '/',
  server: {
    host: '127.0.0.1',
    proxy: {
      '/api': 'http://127.0.0.1:8080',
    },
  },
  build: { outDir: 'dist', sourcemap: false },
});
