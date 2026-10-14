import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API binds to 127.0.0.1:8000; the dev server proxies /api to it.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
