import { defineConfig } from "vitest/config";

// Testy czystych funkcji: bez wtyczek React Router i Tailwinda z vite.config.ts.
export default defineConfig({
  test: {
    environment: "node",
    include: ["app/**/*.test.ts"],
  },
});
