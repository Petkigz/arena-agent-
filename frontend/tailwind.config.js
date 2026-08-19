/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Arena color palette
        background: {
          primary: '#0F172A',    // dark slate
          secondary: '#1E293B',  // slate
          surface: '#334155',    // lighter slate
        },
        text: {
          primary: '#F1F5F9',    // off-white
          secondary: '#94A3B8',  // gray
          muted: '#64748B',      // dark gray
        },
        accent: {
          primary: '#3B82F6',    // blue
          success: '#10B981',    // green
          warning: '#F59E0B',    // amber
          error: '#EF4444',      // red
        },
        presence: {
          idle: '#3B82F6',       // blue, slow pulse
          working: '#F59E0B',    // amber, fast pulse
          listening: '#10B981',  // green, pulsing
          speaking: '#8B5CF6',   // purple, pulsing
        },
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
