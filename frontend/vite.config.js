import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const backend = {
  target: process.env.API_PROXY_TARGET || "http://localhost:8000",
  // "start" runs before the outgoing headers are copied from req.
  configure: (proxy) => proxy.on("start", (req) => (req.headers["x-forwarded-for"] = req.socket.remoteAddress)),
};

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // No CSP here: the dev server needs inline scripts for React refresh.
    headers: { "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer" },
    // Not Vite's default 5173: another local project uses it. strictPort fails loudly instead of picking a random port.
    port: 5174,
    strictPort: true,
    // Frontend calls /api/...; Vite forwards it to FastAPI.
    // Overwrite X-Forwarded-For with the real browser IP so the backend rate-limits per user, not per proxy.
    // Appending (xfwd) would keep a client-sent value first, letting anyone pick a fresh IP per request.
    // The backend has no host port, so Swagger UI and its schema come through here too.
    proxy: { "/api": backend, "/docs": backend, "/openapi.json": backend },
  },
});
