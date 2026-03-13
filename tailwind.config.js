/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        cyber: {
          bg:     '#050d1a',
          panel:  '#0a1628',
          card:   '#0d1f38',
          border: '#1a3a5c',
          cyan:   '#00d4ff',
          green:  '#00ff88',
          red:    '#ff3366',
          yellow: '#ffcc00',
          purple: '#a855f7',
          muted:  '#4a6080',
          text:   '#c8d8e8',
        },
      },
      fontFamily: {
        mono: ['"Fira Code"', 'Consolas', '"Courier New"', 'monospace'],
      },
      animation: {
        'pulse-slow': 'pulse 3s ease-in-out infinite',
        'glow-cyan':  'glowCyan 2s ease-in-out infinite alternate',
        'glow-green': 'glowGreen 2s ease-in-out infinite alternate',
        'glow-red':   'glowRed 2s ease-in-out infinite alternate',
        'scan-line':  'scanLine 3s linear infinite',
        'border-run': 'borderRun 2s linear infinite',
        'float':      'float 4s ease-in-out infinite',
        'fade-in':    'fadeIn 0.5s ease-out forwards',
        'slide-up':   'slideUp 0.4s ease-out forwards',
        'spin-slow':  'spin 8s linear infinite',
      },
      keyframes: {
        glowCyan: {
          '0%':   { boxShadow: '0 0 5px #00d4ff44, 0 0 10px #00d4ff22' },
          '100%': { boxShadow: '0 0 20px #00d4ff, 0 0 40px #00d4ff88' },
        },
        glowGreen: {
          '0%':   { boxShadow: '0 0 5px #00ff8844, 0 0 10px #00ff8822' },
          '100%': { boxShadow: '0 0 20px #00ff88, 0 0 40px #00ff8888' },
        },
        glowRed: {
          '0%':   { boxShadow: '0 0 5px #ff336644, 0 0 10px #ff336622' },
          '100%': { boxShadow: '0 0 20px #ff3366, 0 0 40px #ff336688' },
        },
        scanLine: {
          '0%':   { top: '-2px', opacity: '1' },
          '90%':  { opacity: '1' },
          '100%': { top: '100%', opacity: '0' },
        },
        borderRun: {
          '0%':   { backgroundPosition: '0% 0%' },
          '100%': { backgroundPosition: '200% 0%' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%':      { transform: 'translateY(-8px)' },
        },
        fadeIn: {
          from: { opacity: '0' },
          to:   { opacity: '1' },
        },
        slideUp: {
          from: { opacity: '0', transform: 'translateY(20px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
}
