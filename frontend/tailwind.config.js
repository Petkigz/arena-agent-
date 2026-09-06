/** @type {import('tailwindcss').Config} */
// Design tokens: design/tokens.json is the SINGLE SOURCE OF TRUTH shared with
// the desktop client (desktop/design_tokens.py). Never hardcode hex colors
// here — derive them from the tokens so the two clients cannot drift.
import tokens from '../design/tokens.json';

// Full 11-state Beanie presence palette (previously only 4 states existed here).
const presenceColors = Object.fromEntries(
  Object.entries(tokens.beanie.states).map(([state, spec]) => [state, spec.color]),
);
const accentColors = tokens.color.accent;
const darkBackground = tokens.color.themes.dark.background;
// Elevation scale comes from the shared design system (design/tokens.json).
const shadows = tokens.shadow;

export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      boxShadow: shadows,
      colors: {
        // Theme-aware colors using CSS variables
        background: {
          primary: 'var(--color-background-primary)',
          secondary: 'var(--color-background-secondary)',
          surface: 'var(--color-background-surface)',
        },
        text: {
          primary: 'var(--color-text-primary)',
          secondary: 'var(--color-text-secondary)',
          muted: 'var(--color-text-muted)',
        },
        accent: accentColors,
        presence: presenceColors,
        // Legacy dark-only colors for backward compatibility
        'background-dark': darkBackground,
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      animation: {
        'pulse-slow': 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'pulse-fast': 'pulse 1s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade-in': 'fadeIn 0.3s ease-in-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'slide-down': 'slideDown 0.3s ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { transform: 'translateY(10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        slideDown: {
          '0%': { transform: 'translateY(-10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
      },
    },
  },
  plugins: [],
}
