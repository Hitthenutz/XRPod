import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';

// The HUD's API is served by the Pi (pi-agent/agent.py). In development,
// /api is forwarded to it: run the agent locally (default) or point
// POD_URL at the real Pi, e.g. POD_URL=http://xrpod.local:8080 npm run dev
const POD_URL = process.env.POD_URL ?? 'http://localhost:8080';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    // changeOrigin stays false so the Pi's same-origin check sees the
    // dev server's Host and Origin, which match.
    proxy: { '/api': { target: POD_URL } },
  },
});
