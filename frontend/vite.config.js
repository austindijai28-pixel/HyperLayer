import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// HOST_IP note: during `npm run dev` Vite's own dev server does NOT proxy
// the WebSocket to FastAPI by default. For the real two-laptop LAN demo,
// build the frontend (`npm run build`) and let FastAPI serve the static
// bundle from one origin/port (see backend/app/main.py) - that's the
// configuration MILESTONE 2 asks for. This dev proxy is only for local
// development convenience on a single machine.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // listen on 0.0.0.0 so it's reachable during dev too
    port: 5173,
    proxy: {
      "/ws": {
        target: "ws://127.0.0.1:8000",
        ws: true,
      },
      "/api": {
        target: "http://127.0.0.1:8000",
      },
    },
  },
  build: {
    outDir: "dist",
  },
});
