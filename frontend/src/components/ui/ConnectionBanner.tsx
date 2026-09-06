import { useEffect, useState } from 'react';
import { Wifi, WifiOff, RefreshCw, X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { webSocketService } from '../../services/websocket';

type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'reconnecting';

export function ConnectionBanner() {
  const [status, setStatus] = useState<ConnectionStatus>(webSocketService.status);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    const unsubscribe = webSocketService.onStatusChange((s) => {
      setStatus(s);
      if (s === 'connected') setDismissed(false);
    });
    return unsubscribe;
  }, []);

  if (status === 'connected' || dismissed) return null;

  const handleReconnect = () => {
    webSocketService.disconnect();
    setTimeout(() => {
      webSocketService.connect(`ws://${window.location.hostname}:8000/ws`);
    }, 100);
  };

  const config = {
    disconnected: {
      icon: WifiOff,
      bg: 'bg-accent-error/90 border-accent-error',
      text: 'Disconnected from Arena backend',
      showReconnect: true,
    },
    connecting: {
      icon: RefreshCw,
      bg: 'bg-accent-warning/90 border-accent-warning',
      text: 'Connecting to Arena...',
      showReconnect: false,
    },
    reconnecting: {
      icon: RefreshCw,
      bg: 'bg-accent-warning/90 border-accent-warning',
      text: 'Reconnecting...',
      showReconnect: false,
    },
    connected: {
      icon: Wifi,
      bg: 'bg-accent-success/90 border-accent-success',
      text: 'Connected',
      showReconnect: false,
    },
  };

  const { icon: Icon, bg, text, showReconnect } = config[status];

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
        <div className={`${bg} border-b text-white px-4 py-2 flex items-center gap-3 text-sm`}>
          <motion.div
            animate={status === 'connecting' || status === 'reconnecting' ? { rotate: 360 } : {}}
            transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
          >
            <Icon className="w-4 h-4" />
          </motion.div>
          <span className="flex-1">{text}</span>
          {showReconnect && (
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={handleReconnect}
              className="px-2 py-0.5 bg-white/20 hover:bg-white/30 rounded text-xs font-medium transition-colors"
              aria-label="Reconnect to server"
            >
              Reconnect
            </motion.button>
          )}
          <motion.button
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.9 }}
            onClick={() => setDismissed(true)}
            className="p-0.5 hover:bg-white/20 rounded transition-colors"
            aria-label="Dismiss notification"
          >
            <X className="w-4 h-4" />
          </motion.button>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
