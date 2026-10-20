import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  base: mode === 'admin' ? '/admin/' : '/',
  define: { __ADMIN__: JSON.stringify(mode === 'admin') },
  build: {
    outDir: mode === 'admin' ? 'dist/p2' : 'dist/p1',
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          validation: ['ajv/dist/2020', 'ajv-formats'],
          markdown: ['react-markdown'],
        },
      },
    },
  },
  server: {
    fs: { allow: ['..'] },
    proxy: {
      '/api': { target: process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000', changeOrigin: false },
      '/ws': { target: process.env.WS_PROXY_TARGET || 'ws://127.0.0.1:8000', ws: true },
    },
  },
  test: { environment: 'jsdom', include: ['tests/**/*.test.{ts,tsx}'] },
}));
