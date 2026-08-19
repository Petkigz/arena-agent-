/**
 * Theme utility functions for working with themes in the application
 */

import { useAppearanceSettingsStore } from '../stores/appearanceSettingsStore';

/**
 * Get the currently resolved theme (respects system preference when theme is 'system')
 */
export function getResolvedTheme(): 'dark' | 'light' {
  const theme = useAppearanceSettingsStore.getState().theme;
  
  if (theme !== 'system') return theme;
  
  if (typeof window === 'undefined') return 'dark';
  
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

/**
 * Check if the current theme is dark
 */
export function isDarkTheme(): boolean {
  return getResolvedTheme() === 'dark';
}

/**
 * Check if the current theme is light
 */
export function isLightTheme(): boolean {
  return getResolvedTheme() === 'light';
}

/**
 * Get theme-aware color values from CSS variables
 */
export function getThemeColor(colorName: string): string {
  if (typeof window === 'undefined') return '';
  
  const style = getComputedStyle(document.documentElement);
  return style.getPropertyValue(`--color-${colorName}`).trim();
}

/**
 * Theme color palette for use in JavaScript/Canvas/SVG
 */
export const themeColors = {
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
  accent: {
    primary: '#3B82F6',
    success: '#10B981',
    warning: '#F59E0B',
    error: '#EF4444',
  },
};

/**
 * Hook to subscribe to theme changes
 */
export function useTheme() {
  const theme = useAppearanceSettingsStore((state) => state.theme);
  const resolved = getResolvedTheme();
  
  return {
    theme,
    resolved,
    isDark: resolved === 'dark',
    isLight: resolved === 'light',
  };
}
