import { useEffect } from 'react';
import { useAppearanceSettingsStore } from '../stores/appearanceSettingsStore';

/**
 * Hook to apply accessibility settings globally
 */
export function useAccessibility() {
  const { highContrast, largeText, reducedMotion } = useAppearanceSettingsStore();

  useEffect(() => {
    const root = document.documentElement;

    // Apply high contrast mode
    if (highContrast) {
      root.classList.add('high-contrast');
    } else {
      root.classList.remove('high-contrast');
    }

    // Apply large text mode
    if (largeText) {
      root.classList.add('large-text');
    } else {
      root.classList.remove('large-text');
    }

    // Apply reduced motion mode
    if (reducedMotion) {
      root.classList.add('reduced-motion');
    } else {
      root.classList.remove('reduced-motion');
    }
  }, [highContrast, largeText, reducedMotion]);
}

/**
 * Announce message to screen readers
 */
export function announceToScreenReader(message: string, priority: 'polite' | 'assertive' = 'polite') {
  // Create or get the live region element
  let liveRegion = document.getElementById('sr-live-region');
  
  if (!liveRegion) {
    liveRegion = document.createElement('div');
    liveRegion.id = 'sr-live-region';
    liveRegion.setAttribute('aria-live', priority);
    liveRegion.setAttribute('aria-atomic', 'true');
    liveRegion.style.position = 'absolute';
    liveRegion.style.left = '-10000px';
    liveRegion.style.width = '1px';
    liveRegion.style.height = '1px';
    liveRegion.style.overflow = 'hidden';
    document.body.appendChild(liveRegion);
  }

  // Clear previous message
  liveRegion.textContent = '';
  
  // Set new message after a brief delay to ensure screen readers pick it up
  setTimeout(() => {
    liveRegion!.textContent = message;
  }, 100);
}

/**
 * Manage focus trap for modals and dialogs
 */
export function useFocusTrap(isActive: boolean) {
  useEffect(() => {
    if (!isActive) return;

    const focusableElements = document.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    
    const firstElement = focusableElements[0] as HTMLElement;
    const lastElement = focusableElements[focusableElements.length - 1] as HTMLElement;

    const handleTabKey = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return;

      if (e.shiftKey) {
        // Shift + Tab
        if (document.activeElement === firstElement) {
          e.preventDefault();
          lastElement?.focus();
        }
      } else {
        // Tab
        if (document.activeElement === lastElement) {
          e.preventDefault();
          firstElement?.focus();
        }
      }
    };

    document.addEventListener('keydown', handleTabKey);
    
    // Focus first element
    firstElement?.focus();

    return () => {
      document.removeEventListener('keydown', handleTabKey);
    };
  }, [isActive]);
}

/**
 * Skip to main content link handler
 */
export function useSkipToContent() {
  useEffect(() => {
    const handleSkipLink = (e: KeyboardEvent) => {
      if (e.key === 'Tab' && !e.shiftKey) {
        const skipLink = document.querySelector('.skip-to-content') as HTMLElement;
        if (skipLink && document.activeElement === skipLink) {
          e.preventDefault();
          const mainContent = document.querySelector('main') as HTMLElement;
          if (mainContent) {
            mainContent.setAttribute('tabindex', '-1');
            mainContent.focus();
          }
        }
      }
    };

    document.addEventListener('keydown', handleSkipLink);
    return () => document.removeEventListener('keydown', handleSkipLink);
  }, []);
}
