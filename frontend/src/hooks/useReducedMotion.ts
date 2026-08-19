import { useMediaQuery } from './useMediaQuery';
import { useAppearanceSettingsStore } from '../stores/appearanceSettingsStore';

/**
 * Returns true if animations should be reduced/disabled.
 * Respects both the browser's prefers-reduced-motion media query
 * and the user's appearance settings.
 */
export function useReducedMotion(): boolean {
  const prefersReducedMotion = useMediaQuery('(prefers-reduced-motion: reduce)');
  const showAnimations = useAppearanceSettingsStore((s) => s.showAnimations);
  
  return prefersReducedMotion || !showAnimations;
}
