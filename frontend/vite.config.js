import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Frontend calls /api/...; Vite forwards it to FastAPI.
    // xfwd sends the browser's IP as X-Forwarded-For, so the backend rate-limits per user, not per proxy.
    proxy: { "/api": { target: process.env.API_PROXY_TARGET || "http://localhost:8000", xfwd: true } },
  },
});
