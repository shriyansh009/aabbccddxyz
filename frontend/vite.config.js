import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the React app proxies /api to the FastAPI server.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": process.env.API_URL || "http://localhost:8000" } },
});
