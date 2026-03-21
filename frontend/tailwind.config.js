/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // ── Background hierarchy ──────────────────────────
        bg: {
          0:       '#020617',            // deepest — body
          1:       '#050D1A',            // page background
          2:       '#0A1628',            // section
          3:       '#0F1F35',            // card surface
          4:       '#162240',            // elevated card
          glass:   'rgba(10,22,40,0.75)',// glassmorphism
        },
        // ── Accents ───────────────────────────────────────
        accent: {
          DEFAULT:  '#7C3AED',
          light:    '#8B5CF6',
          muted:    'rgba(124,58,237,0.15)',
          border:   'rgba(124,58,237,0.35)',
        },
        sky: {
          DEFAULT:  '#0EA5E9',
          muted:    'rgba(14,165,233,0.12)',
        },
        gold: {
          DEFAULT:  '#EAB308',
          muted:    'rgba(234,179,8,0.12)',
        },
        // ── Semantic signals ──────────────────────────────
        bull: {
          DEFAULT:  '#22C55E',
          bright:   '#4ADE80',
          muted:    'rgba(34,197,94,0.12)',
          border:   'rgba(34,197,94,0.25)',
        },
        bear: {
          DEFAULT:  '#EF4444',
          bright:   '#F87171',
          muted:    'rgba(239,68,68,0.12)',
          border:   'rgba(239,68,68,0.25)',
        },
        warn: {
          DEFAULT:  '#F97316',
          muted:    'rgba(249,115,22,0.12)',
        },
        // ── Text ─────────────────────────────────────────
        t: {
          1:  '#F1F5F9',
          2:  '#CBD5E1',
          3:  '#94A3B8',
          4:  '#475569',
          5:  '#334155',
        },
        // ── Borders ───────────────────────────────────────
        line: {
          1:  'rgba(148,163,184,0.07)',
          2:  'rgba(148,163,184,0.13)',
          3:  'rgba(148,163,184,0.22)',
        },
      },
      fontFamily: {
        sans:  ['Inter', 'Noto Sans TC', 'system-ui', 'sans-serif'],
        mono:  ['Fira Code', 'JetBrains Mono', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.625rem', { lineHeight: '0.875rem' }],
      },
      boxShadow: {
        'card':          '0 1px 3px rgba(0,0,0,0.4), 0 4px 16px rgba(0,0,0,0.3)',
        'card-hover':    '0 4px 24px rgba(0,0,0,0.5), 0 0 0 1px rgba(148,163,184,0.13)',
        'glow-accent':   '0 0 20px rgba(124,58,237,0.25)',
        'glow-bull':     '0 0 12px rgba(34,197,94,0.3)',
        'glow-bear':     '0 0 12px rgba(239,68,68,0.3)',
        'glow-gold':     '0 0 12px rgba(234,179,8,0.25)',
        'elevated':      '0 8px 32px rgba(0,0,0,0.6)',
      },
      borderRadius: {
        DEFAULT: '8px',
        sm:  '5px',
        md:  '10px',
        lg:  '14px',
        xl:  '18px',
      },
      animation: {
        'fade-in':    'fadeIn 200ms ease-out',
        'slide-up':   'slideUp 300ms cubic-bezier(0.16,1,0.3,1)',
        'pulse-dot':  'pulseDot 2s ease-in-out infinite',
        'ticker':     'ticker 30s linear infinite',
        'shimmer':    'shimmer 1.6s ease-in-out infinite',
        'glow':       'glowPulse 3s ease-in-out infinite',
        'count-up':   'countUp 600ms cubic-bezier(0.16,1,0.3,1)',
      },
      keyframes: {
        fadeIn:    { from: { opacity:'0' }, to: { opacity:'1' } },
        slideUp:   { from: { opacity:'0', transform:'translateY(10px)' }, to: { opacity:'1', transform:'translateY(0)' } },
        pulseDot:  { '0%,100%': { opacity:'0.5', transform:'scale(1)' }, '50%': { opacity:'1', transform:'scale(1.3)' } },
        ticker:    { '0%': { transform:'translateX(0)' }, '100%': { transform:'translateX(-50%)' } },
        shimmer:   { '0%': { backgroundPosition:'-400% 0' }, '100%': { backgroundPosition:'400% 0' } },
        glowPulse: { '0%,100%': { opacity:'0.7' }, '50%': { opacity:'1' } },
        countUp:   { from: { transform:'translateY(4px)', opacity:'0' }, to: { transform:'translateY(0)', opacity:'1' } },
      },
    },
  },
  plugins: [],
}
