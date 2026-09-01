import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev proxy: the SPA calls /api and /artifacts on its own origin; Vite forwards
// them to the FastAPI backend on :8099.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5180,
    proxy: {
      "/api": "http://localhost:8099",
      "/artifacts": "http://localhost:8099",
    },
  },
});
