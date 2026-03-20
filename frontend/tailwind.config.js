/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Background hierarchy (5-level)
        bg: {
          void:     '#0B0F19',
          base:     '#0F172A',
          surface:  '#1E293B',
          card:     'rgba(30, 41, 59, 0.7)',
          elevated: 'rgba(30, 41, 59, 0.9)',
          hover:    'rgba(51, 65, 85, 0.5)',
        },
        // Primary (Gold - Trust)
        primary: {
          DEFAULT: '#F59E0B',
          dim:     'rgba(245, 158, 11, 0.08)',
          glow:    'rgba(245, 158, 11, 0.12)',
        },
        // Accent (Purple - Tech)
        accent: {
          DEFAULT: '#8B5CF6',
          dim:     'rgba(139, 92, 246, 0.08)',
          glow:    'rgba(139, 92, 246, 0.15)',
          solid:   '#7C3AED',
        },
        // Semantic
        bullish:  '#34D399',
        bearish:  '#F87171',
        warning:  '#FBBF24',
        neutral:  '#94A3B8',
        // Text
        text: {
          1: '#F8FAFC',
          2: '#94A3B8',
          3: '#64748B',
        },
        // Border
        border: {
          DEFAULT: 'rgba(148, 163, 184, 0.1)',
          subtle:  'rgba(148, 163, 184, 0.06)',
          hover:   'rgba(148, 163, 184, 0.2)',
          active:  'rgba(139, 92, 246, 0.4)',
        },
      },
      fontFamily: {
        sans:    ['Inter', 'Noto Sans TC', 'system-ui', 'sans-serif'],
        mono:    ['JetBrains Mono', 'Fira Code', 'monospace'],
        heading: ['Inter', 'Noto Sans TC', 'sans-serif'],
      },
      boxShadow: {
        card:         '0 4px 24px rgba(0, 0, 0, 0.3)',
        'card-hover': '0 8px 40px rgba(0, 0, 0, 0.5)',
        elevated:     '0 12px 48px rgba(0, 0, 0, 0.6)',
        'glow-primary': '0 0 20px rgba(245, 158, 11, 0.08)',
        'glow-accent':  '0 0 20px rgba(139, 92, 246, 0.1)',
      },
      borderRadius: {
        DEFAULT: '12px',
        lg:      '16px',
        sm:      '8px',
      },
      transitionTimingFunction: {
        'out-expo': 'cubic-bezier(0.16, 1, 0.3, 1)',
      },
      animation: {
        'fade-in':    'fadeIn 300ms ease-out',
        'slide-up':   'slideUp 320ms cubic-bezier(0.16, 1, 0.3, 1)',
        'shimmer':    'shimmer 1.5s infinite linear',
        'spin-slow':  'spin 2s linear infinite',
        'stagger-in': 'staggerIn 400ms cubic-bezier(0.16, 1, 0.3, 1) both',
      },
      keyframes: {
        fadeIn: {
          from: { opacity: '0' },
          to:   { opacity: '1' },
        },
        slideUp: {
          from: { opacity: '0', transform: 'translateY(12px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
        shimmer: {
          '0%':   { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        staggerIn: {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
      },
      spacing: {
        'sidebar': '240px',
        'topbar':  '56px',
      },
    },
  },
  plugins: [],
}
