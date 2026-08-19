import { useSyncExternalStore } from 'react';

/**
 * Hook to subscribe to a media query.
 * Uses useSyncExternalStore for tear-free reads (no setState in effect).
 */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (callback) => {
      const mediaQuery = window.matchMedia(query);
      mediaQuery.addEventListener('change', callback);
      return () => mediaQuery.removeEventListener('change', callback);
    },
    () => window.matchMedia(query).matches,
    () => false // SSR fallback
  );
}
