/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg:       { base: '#0D1117', card: '#161B22', hover: '#21262D' },
        border:   { DEFAULT: '#30363D' },
        text:     { primary: '#E6EDF3', secondary: '#8B949E' },
        accent:   '#1B9AAA',
        bullish:  '#3FB950',
        bearish:  '#F85149',
        neutral:  '#8B949E',
        warning:  '#D29922',
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
        sans: ['Noto Sans TC', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
