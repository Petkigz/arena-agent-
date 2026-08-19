import { useEffect, useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { MessageCircle, Brain, Settings, Plus, Trash2, File, Code, ChevronLeft, ChevronRight } from 'lucide-react';
import { cn } from '../../utils/cn';
import { Button } from '../ui/Button';
import { ConversationFilters } from '../chat/ConversationFilters';
import { useConversationStore, useLayoutStore } from '../../stores';
import { webSocketService } from '../../services/websocket';
import { formatDistanceToNow } from 'date-fns';

type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'reconnecting';

const statusConfig: Record<ConnectionStatus, { color: string; label: string }> = {
  connected: { color: 'bg-green-500', label: 'Online' },
  connecting: { color: 'bg-yellow-500', label: 'Connecting...' },
  reconnecting: { color: 'bg-yellow-500', label: 'Reconnecting...' },
  disconnected: { color: 'bg-red-500', label: 'Offline' },
};

export function Sidebar() {
  const navigate = useNavigate();
  const { conversations, currentConversation, createConversation, setCurrentConversation, removeConversation } =
    useConversationStore();
  const { sidebarCollapsed, toggleSidebar } = useLayoutStore();

  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>(
    webSocketService.status
  );
  const [showFilters, setShowFilters] = useState(false);

  // Track WebSocket connection status
  useEffect(() => {
    const unsubscribe = webSocketService.onStatusChange((status) => {
      setConnectionStatus(status);
    });
    return unsubscribe;
  }, []);

  const handleNewConversation = async () => {
    const id = await createConversation();
    setCurrentConversation(useConversationStore.getState().conversations.find((c) => c.id === id) || null);
    navigate('/chat');
  };

  const handleSelectConversation = (id: string) => {
    const conv = conversations.find((c) => c.id === id);
    if (conv) {
      setCurrentConversation(conv);
      navigate('/chat');
    }
  };

  const handleDeleteConversation = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    removeConversation(id);
  };

  const links = [
    { to: '/chat', icon: MessageCircle, label: 'Chats' },
    { to: '/pansophy', icon: Brain, label: 'Pansophy' },
    { to: '/files', icon: File, label: 'Files' },
    { to: '/code', icon: Code, label: 'Code' },
    { to: '/settings', icon: Settings, label: 'Settings' },
  ];

  const status = statusConfig[connectionStatus];

  return (
    <aside
      className={cn(
        'bg-background-secondary border-r border-background-surface flex flex-col transition-all duration-300',
        sidebarCollapsed ? 'w-16' : 'w-64'
      )}
    >
      {/* Presence indicator with real connection status */}
      <div className="p-4 border-b border-background-surface" data-tutorial="presence-orb">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-accent-primary animate-pulse-slow flex-shrink-0" />
          {!sidebarCollapsed && (
            <div className="flex-1 min-w-0">
              <h2 className="font-semibold text-text-primary">Arena</h2>
              <div className="flex items-center gap-1.5">
                <span className={`w-2 h-2 rounded-full ${status.color}`} />
                <p className="text-xs text-text-muted">{status.label}</p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* New conversation button */}
      <div className={cn('p-4 space-y-3', sidebarCollapsed && 'px-2')}>
        <Button
          className={cn('w-full', sidebarCollapsed && 'px-2')}
          variant="primary"
          onClick={handleNewConversation}
        >
          <Plus className="w-4 h-4" />
          {!sidebarCollapsed && <span className="ml-2">New Conversation</span>}
        </Button>

        {/* Filters toggle */}
        {!sidebarCollapsed && conversations.length > 0 && (
          <button
            onClick={() => setShowFilters(!showFilters)}
            className="w-full text-sm text-text-muted hover:text-text-primary transition-colors"
          >
            {showFilters ? 'Hide Filters' : 'Show Filters'}
          </button>
        )}

        {/* Filters panel */}
        {showFilters && !sidebarCollapsed && <ConversationFilters />}
      </div>

      {/* Conversation list */}
      {!sidebarCollapsed && conversations.length > 0 && (
        <div className="px-2 mb-2" data-tutorial="conversation-list">
          <p className="px-3 text-xs font-medium text-text-muted uppercase tracking-wide mb-1">
            Conversations
          </p>
          <div className="space-y-0.5 max-h-48 overflow-y-auto">
            {conversations.map((conv) => {
              const isActive = currentConversation?.id === conv.id;
              return (
                <div
                  key={conv.id}
                  onClick={() => handleSelectConversation(conv.id)}
                  className={cn(
                    'group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors',
                    isActive
                      ? 'bg-accent-primary/20 text-text-primary'
                      : 'text-text-secondary hover:bg-background-surface hover:text-text-primary'
                  )}
                >
                  <MessageCircle className="w-4 h-4 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{conv.title}</p>
                    <p className="text-xs text-text-muted truncate">
                      {formatDistanceToNow(new Date(conv.updatedAt), { addSuffix: true })}
                    </p>
                  </div>
                  <button
                    onClick={(e) => handleDeleteConversation(e, conv.id)}
                    className="opacity-0 group-hover:opacity-100 p-1 text-text-muted hover:text-accent-error transition-all"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Navigation links */}
      <nav className={cn('flex-1 overflow-y-auto px-2', sidebarCollapsed && 'px-1')}>
        {links.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            data-tutorial={`nav-${label.toLowerCase()}`}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 px-3 py-2 rounded-lg mb-1 transition-colors',
                isActive
                  ? 'bg-accent-primary text-white'
                  : 'text-text-secondary hover:bg-background-surface hover:text-text-primary',
                sidebarCollapsed && 'justify-center px-2'
              )}
            >
              <Icon className="w-5 h-5 flex-shrink-0" />
              {!sidebarCollapsed && <span className="font-medium">{label}</span>}
            </NavLink>
          ))}
      </nav>

      {/* Collapse toggle */}
      <div className="p-2 border-t border-background-surface">
        <button
          onClick={toggleSidebar}
          className="w-full flex items-center justify-center p-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-background-surface transition-colors"
          aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {sidebarCollapsed ? (
            <ChevronRight className="w-5 h-5" />
          ) : (
            <>
              <ChevronLeft className="w-5 h-5" />
              <span className="ml-2 text-sm">Collapse</span>
            </>
          )}
        </button>
      </div>
    </aside>
  );
}
