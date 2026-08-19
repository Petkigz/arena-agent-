import { useState, useEffect, useRef, useCallback, useMemo } from 'react';

/**
 * Debounces a value by the specified delay.
 * Useful for search inputs and other high-frequency updates.
 */
export function useDebounce<T>(value: T, delay: number = 300): T {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => {
      clearTimeout(handler);
    };
  }, [value, delay]);

  return debouncedValue;
}

/**
 * Creates a debounced callback function.
 * The callback will only be invoked after the specified delay
 * has passed since the last invocation.
 */
export function useDebouncedCallback<T extends (...args: any[]) => any>(
  callback: T,
  delay: number = 300
): T {
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const callbackRef = useRef(callback);

  // Update callback ref on each render
  useEffect(() => {
    callbackRef.current = callback;
  }, [callback]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, [delay]);

  return useCallback(
    ((...args: Parameters<T>) => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
      timeoutRef.current = setTimeout(() => {
        callbackRef.current(...args);
      }, delay);
    }) as T,
    [delay]
  );
}

/**
 * Throttles a value update to the specified interval.
 * Useful for scroll/resize events.
 */
export function useThrottle<T>(value: T, interval: number = 200): T {
  const [throttledValue, setThrottledValue] = useState(value);
  const lastUpdated = useRef(Date.now());

  useEffect(() => {
    const now = Date.now();
    if (now >= lastUpdated.current + interval) {
      lastUpdated.current = now;
      setThrottledValue(value);
    } else {
      const timer = setTimeout(() => {
        lastUpdated.current = Date.now();
        setThrottledValue(value);
      }, interval - (now - lastUpdated.current));

      return () => clearTimeout(timer);
    }
  }, [value, interval]);

  return throttledValue;
}

/**
 * Deep comparison memoization hook.
 * Returns the same reference if the value hasn't changed deeply.
 */
export function useDeepMemo<T>(value: T): T {
  const ref = useRef<T>(value);
  const signalRef = useRef(0);

  const isEqual = useCallback((a: T, b: T): boolean => {
    if (a === b) return true;
    if (typeof a !== typeof b) return false;
    if (a === null || b === null) return a === b;
    if (typeof a !== 'object') return a === b;
    
    if (Array.isArray(a) && Array.isArray(b)) {
      if (a.length !== b.length) return false;
      return a.every((item, i) => isEqual(item, b[i]));
    }
    
    if (Array.isArray(a) || Array.isArray(b)) return false;
    
    const keysA = Object.keys(a as Record<string, unknown>);
    const keysB = Object.keys(b as Record<string, unknown>);
    if (keysA.length !== keysB.length) return false;
    
    return keysA.every((key) =>
      isEqual(
        (a as Record<string, unknown>)[key] as T,
        (b as Record<string, unknown>)[key] as T
      )
    );
  }, []);

  if (!isEqual(ref.current, value)) {
    ref.current = value;
    signalRef.current += 1;
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => ref.current, [signalRef.current]);
}

/**
 * Prevents expensive renders by deferring updates.
 * Returns a deferred value that updates after a brief delay.
 */
export function useDeferredValue<T>(value: T, timeout: number = 200): T {
  const [deferredValue, setDeferredValue] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDeferredValue(value);
    }, timeout);

    return () => clearTimeout(timer);
  }, [value, timeout]);

  return deferredValue;
}
