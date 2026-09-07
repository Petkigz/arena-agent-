import { useState, useEffect, useCallback } from 'react';
import { apiUrl } from '../services/api';

export interface OnlineStatus {
  isOnline: boolean;
  backendConnected: boolean;
  lastChecked: number;
}

/**
 * Hook to monitor both internet connectivity and local backend status.
 * For fully offline PC operation, "online" means the local backend is reachable.
 */
export function useOnlineStatus(): OnlineStatus {
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const [backendConnected, setBackendConnected] = useState(false);
  const [lastChecked, setLastChecked] = useState(Date.now());

  // Monitor browser online/offline events
  useEffect(() => {
    const handleOnline = () => {
      setIsOnline(true);
      setLastChecked(Date.now());
    };
    const handleOffline = () => {
      setIsOnline(false);
      setLastChecked(Date.now());
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  // Periodically check if the local backend is reachable
  const checkBackend = useCallback(async () => {
    try {
      const healthUrl = apiUrl('/health');
      const response = await fetch(healthUrl, { 
        method: 'GET',
        signal: AbortSignal.timeout(3000),
      });
      setBackendConnected(response.ok);
    } catch {
      // Backend not reachable, but that's OK for offline mode
      setBackendConnected(false);
    }
    setLastChecked(Date.now());
  }, []);

  useEffect(() => {
    checkBackend();
    const interval = setInterval(checkBackend, 30000); // Check every 30s
    return () => clearInterval(interval);
  }, [checkBackend]);

  // For fully offline PC operation, the app is "online" if the local backend is running
  // Internet connectivity is not required
  return {
    isOnline,
    backendConnected,
    lastChecked,
  };
}
