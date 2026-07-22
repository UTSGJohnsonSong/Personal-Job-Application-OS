import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0b0f17",
        panel: "#111827",
        muted: "#6b7280",
        accent: "#3b82f6",
      },
    },
  },
  plugins: [],
};

export default config;
