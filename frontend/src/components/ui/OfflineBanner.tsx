import { useState, useEffect } from 'react';
import { Server, RefreshCw, X, CheckCircle } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useOnlineStatus } from '../../hooks/useOnlineStatus';

/**
 * Offline banner that shows the current connectivity status.
 * For fully offline PC operation, the key indicator is whether
 * the local backend is running — internet is not required.
 */
export function OfflineBanner() {
  const { isOnline, backendConnected } = useOnlineStatus();
  const [dismissed, setDismissed] = useState(false);
  const [showBanner, setShowBanner] = useState(false);

  // Show banner when backend is not connected
  useEffect(() => {
    if (!backendConnected) {
      setDismissed(false);
      setShowBanner(true);
    } else {
      // Auto-dismiss after 3 seconds when backend connects
      const timer = setTimeout(() => setShowBanner(false), 3000);
      return () => clearTimeout(timer);
    }
  }, [backendConnected]);

  if (!showBanner || dismissed) return null;

  const handleReconnect = () => {
    window.location.reload();
  };

  // Backend is connected — show brief success notification
  if (backendConnected) {
    return (
      <AnimatePresence>
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.3, ease: 'easeInOut' }}
          className="overflow-hidden"
          role="status"
          aria-live="polite"
        >
          <div className="bg-green-900/90 border-b border-green-700 text-white px-4 py-2 flex items-center gap-3 text-sm">
            <CheckCircle className="w-4 h-4" aria-hidden="true" />
            <span className="flex-1">Local backend connected — Arena is ready</span>
          </div>
        </motion.div>
      </AnimatePresence>
    );
  }

  // Backend is not connected — show helpful guidance
  return (
    <AnimatePresence>
      <motion.div
        initial={{ height: 0, opacity: 0 }}
        animate={{ height: 'auto', opacity: 1 }}
        exit={{ height: 0, opacity: 0 }}
        transition={{ duration: 0.3, ease: 'easeInOut' }}
        className="overflow-hidden"
        role="alert"
        aria-live="assertive"
      >
        <div className="bg-amber-900/90 border-b border-amber-700 text-white px-4 py-2 flex items-center gap-3 text-sm">
          <Server className="w-4 h-4" aria-hidden="true" />
          <span className="flex-1">
            {isOnline 
              ? 'Local backend not running. Start the Arena backend to use AI features.'
              : 'You\'re offline. Start the Arena backend for AI features, or browse cached conversations.'}
          </span>
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={handleReconnect}
            className="px-2 py-0.5 bg-white/20 hover:bg-white/30 rounded text-xs font-medium transition-colors flex items-center gap-1"
            aria-label="Retry connection"
          >
            <RefreshCw className="w-3 h-3" aria-hidden="true" />
            Retry
          </motion.button>
          <motion.button
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.9 }}
            onClick={() => setDismissed(true)}
            className="p-0.5 hover:bg-white/20 rounded transition-colors"
            aria-label="Dismiss notification"
          >
            <X className="w-4 h-4" aria-hidden="true" />
          </motion.button>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
