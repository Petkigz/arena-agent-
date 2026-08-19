import { useEffect } from 'react';
import { useAppearanceSettingsStore } from '../stores/appearanceSettingsStore';

const FONT_SIZE_MAP = {
  small: '12px',
  medium: '14px',
  large: '16px',
} as const;

function getResolvedTheme(theme: 'dark' | 'light' | 'system'): 'dark' | 'light' {
  if (theme !== 'system') return theme;
  if (typeof window === 'undefined') return 'dark';
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function useThemeApplication() {
  const {
    theme,
    fontSize,
    fontFamily,
    compactMode,
    showAnimations,
    highContrast,
  } = useAppearanceSettingsStore();

  useEffect(() => {
    const root = document.documentElement;
    const resolved = getResolvedTheme(theme);

    // Apply theme class
    root.classList.remove('dark', 'light');
    root.classList.add(resolved);
    root.setAttribute('data-theme', resolved);

    // Apply font size as CSS variable
    root.style.setProperty('--arena-font-size', FONT_SIZE_MAP[fontSize]);

    // Apply font family
    root.style.setProperty('--arena-font-family', fontFamily);

    // Apply compact mode
    if (compactMode) {
      root.classList.add('arena-compact');
    } else {
      root.classList.remove('arena-compact');
    }

    // Apply animations toggle
    if (!showAnimations) {
      root.classList.add('arena-no-animations');
    } else {
      root.classList.remove('arena-no-animations');
    }

    // Apply high contrast
    if (highContrast) {
      root.classList.add('arena-high-contrast');
    } else {
      root.classList.remove('arena-high-contrast');
    }

    // Listen for system theme changes when in 'system' mode
    if (theme === 'system') {
      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
      const handler = () => {
        const newResolved = mediaQuery.matches ? 'dark' : 'light';
        root.classList.remove('dark', 'light');
        root.classList.add(newResolved);
        root.setAttribute('data-theme', newResolved);
      };
      mediaQuery.addEventListener('change', handler);
      return () => mediaQuery.removeEventListener('change', handler);
    }
  }, [theme, fontSize, fontFamily, compactMode, showAnimations, highContrast]);
}

export function isQuietHoursActive(start: string, end: string): boolean {
  const now = new Date();
  const currentMinutes = now.getHours() * 60 + now.getMinutes();

  const [startH, startM] = start.split(':').map(Number);
  const [endH, endM] = end.split(':').map(Number);
  const startMinutes = startH * 60 + startM;
  const endMinutes = endH * 60 + endM;

  if (startMinutes <= endMinutes) {
    // Same day range (e.g., 22:00 to 23:59 wouldn't wrap, but 08:00 to 17:00)
    return currentMinutes >= startMinutes && currentMinutes < endMinutes;
  } else {
    // Wraps midnight (e.g., 22:00 to 08:00)
    return currentMinutes >= startMinutes || currentMinutes < endMinutes;
  }
}
