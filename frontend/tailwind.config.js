/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: {
    colors: { ink: { 950: "#07080c", 900: "#0b0d13", 850: "#0f121a", 800: "#141823", 700: "#1c2130", 600: "#262c3f", 500: "#363e57" },
              accent: { DEFAULT: "#8b5cf6", soft: "#a78bfa", cyan: "#22d3ee", lime: "#a3e635", amber: "#fbbf24", rose: "#fb7185" } },
    fontFamily: { sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"], mono: ["JetBrains Mono", "ui-monospace", "monospace"] } } },
  plugins: [],
};
