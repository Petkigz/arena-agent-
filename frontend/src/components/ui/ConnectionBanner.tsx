import { useEffect, useState } from 'react';
import { Wifi, WifiOff, RefreshCw, X } from 'lucide-react';
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
      bg: 'bg-red-900/90 border-red-700',
      text: 'Disconnected from Arena backend',
      showReconnect: true,
    },
    connecting: {
      icon: RefreshCw,
      bg: 'bg-yellow-900/90 border-yellow-700',
      text: 'Connecting to Arena...',
      showReconnect: false,
    },
    reconnecting: {
      icon: RefreshCw,
      bg: 'bg-yellow-900/90 border-yellow-700',
      text: 'Reconnecting...',
      showReconnect: false,
    },
    connected: {
      icon: Wifi,
      bg: 'bg-green-900/90 border-green-700',
      text: 'Connected',
      showReconnect: false,
    },
  };

  const { icon: Icon, bg, text, showReconnect } = config[status];

  return (
    <div className={`${bg} border-b text-white px-4 py-2 flex items-center gap-3 text-sm`}>
      <Icon className={`w-4 h-4 ${status === 'connecting' || status === 'reconnecting' ? 'animate-spin' : ''}`} />
      <span className="flex-1">{text}</span>
      {showReconnect && (
        <button
          onClick={handleReconnect}
          className="px-2 py-0.5 bg-white/20 hover:bg-white/30 rounded text-xs font-medium transition-colors"
        >
          Reconnect
        </button>
      )}
      <button onClick={() => setDismissed(true)} className="p-0.5 hover:bg-white/20 rounded transition-colors">
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}
