/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The backend (FastAPI) runs on :8000. Proxy API + WebSocket + Demo Feed so the app is one origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", rewrite: (p) => p.replace(/^\/api/, "") },
      "/stream": { target: "ws://localhost:8000", ws: true },
      "/demo": { target: "http://localhost:8000" },
    },
  },
  test: { environment: "node" },
});
