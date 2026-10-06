/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        base: {
          950: "#05070a",
          900: "#0a0e14",
          800: "#111722",
          700: "#1a2230",
          600: "#263042",
        },
        accent: {
          500: "#3b82f6",
          400: "#60a5fa",
        },
      },
    },
  },
  plugins: [],
};
