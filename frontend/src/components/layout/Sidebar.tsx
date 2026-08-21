import { useEffect, useState, useCallback, useMemo } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { MessageCircle, Brain, Settings, Plus, File, Code, ChevronLeft, ChevronRight } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { cn } from '../../utils/cn';
import { Button } from '../ui/Button';
import { ConversationFilters } from '../chat/ConversationFilters';
import { ConversationItem } from '../chat/ConversationItem';
import { useConversationStore, useLayoutStore } from '../../stores';
import { webSocketService } from '../../services/websocket';

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

  const handleNewConversation = useCallback(async () => {
    const id = await createConversation();
    setCurrentConversation(useConversationStore.getState().conversations.find((c) => c.id === id) || null);
    navigate('/chat');
  }, [createConversation, setCurrentConversation, navigate]);

  const handleSelectConversation = useCallback((id: string) => {
    const conv = conversations.find((c) => c.id === id);
    if (conv) {
      setCurrentConversation(conv);
      navigate('/chat');
    }
  }, [conversations, setCurrentConversation, navigate]);

  const handleDeleteConversation = useCallback((e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    removeConversation(id);
  }, [removeConversation]);

  const links = useMemo(() => [
    { to: '/chat', icon: MessageCircle, label: 'Chats' },
    { to: '/pansophy', icon: Brain, label: 'Pansophy' },
    { to: '/files', icon: File, label: 'Files' },
    { to: '/code', icon: Code, label: 'Code' },
    { to: '/settings', icon: Settings, label: 'Settings' },
  ], []);

  const status = useMemo(() => statusConfig[connectionStatus], [connectionStatus]);

  return (
    <motion.aside
      initial={{ x: -20, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      aria-label="Application sidebar"
      className={cn(
        'bg-background-secondary border-r border-background-surface flex flex-col transition-all duration-300',
        sidebarCollapsed ? 'w-16' : 'w-64'
      )}
    >
      {/* Presence indicator with real connection status */}
      <div className="p-4 border-b border-background-surface" data-tutorial="presence-orb">
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-full bg-accent-primary animate-pulse-slow flex-shrink-0"
            role="img"
            aria-label="Arena presence indicator"
          />
          {!sidebarCollapsed && (
            <div className="flex-1 min-w-0">
              <h2 className="font-semibold text-text-primary">Arena</h2>
              <div className="flex items-center gap-1.5" role="status" aria-live="polite" aria-atomic="true">
                <span className={`w-2 h-2 rounded-full ${status.color}`} aria-hidden="true" />
                <p className="text-xs text-text-muted">{status.label}</p>
              </div>
            </div>
          )}
          {sidebarCollapsed && (
            <span className="sr-only" role="status" aria-live="polite">{status.label}</span>
          )}
        </div>
      </div>

      {/* New conversation button */}
      <div className={cn('p-4 space-y-3', sidebarCollapsed && 'px-2')}>
        <Button
          className={cn('w-full', sidebarCollapsed && 'px-2')}
          variant="primary"
          onClick={handleNewConversation}
          aria-label={sidebarCollapsed ? 'New conversation' : undefined}
        >
          <Plus className="w-4 h-4" aria-hidden="true" />
          {!sidebarCollapsed && <span className="ml-2">New Conversation</span>}
        </Button>

        {/* Filters toggle */}
        {!sidebarCollapsed && conversations.length > 0 && (
          <button
            onClick={() => setShowFilters(!showFilters)}
            className="w-full text-sm text-text-muted hover:text-text-primary transition-colors"
            aria-expanded={showFilters}
            aria-controls="conversation-filters"
          >
            {showFilters ? 'Hide Filters' : 'Show Filters'}
          </button>
        )}

        {/* Filters panel */}
        {showFilters && !sidebarCollapsed && (
          <div id="conversation-filters" role="region" aria-label="Conversation filters">
            <ConversationFilters />
          </div>
        )}
      </div>

      {/* Conversation list */}
      {!sidebarCollapsed && conversations.length > 0 && (
        <div className="px-2 mb-2" data-tutorial="conversation-list" role="region" aria-label="Conversations">
          <h3 className="px-3 text-xs font-medium text-text-muted uppercase tracking-wide mb-1" id="conversations-heading">
            Conversations
          </h3>
          <ul className="space-y-0.5 max-h-48 overflow-y-auto" role="list" aria-labelledby="conversations-heading">
            <AnimatePresence>
              {conversations.map((conv) => (
                <li key={conv.id} role="listitem">
                  <ConversationItem
                    conversation={conv}
                    isActive={currentConversation?.id === conv.id}
                    onSelect={handleSelectConversation}
                    onDelete={handleDeleteConversation}
                  />
                </li>
              ))}
            </AnimatePresence>
          </ul>
        </div>
      )}

      {/* Navigation links */}
      <nav className={cn('flex-1 overflow-y-auto px-2', sidebarCollapsed && 'px-1')} aria-label="Main navigation">
        <ul className="list-none p-0 m-0" role="list">
          {links.map(({ to, icon: Icon, label }, index) => (
            <motion.li
              key={to}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.2, delay: index * 0.05 }}
              role="listitem"
            >
              <NavLink
                to={to}
                data-tutorial={`nav-${label.toLowerCase()}`}
                aria-label={sidebarCollapsed ? label : undefined}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 px-3 py-2 rounded-lg mb-1 transition-colors',
                    isActive
                      ? 'bg-accent-primary text-white'
                      : 'text-text-secondary hover:bg-background-surface hover:text-text-primary',
                    sidebarCollapsed && 'justify-center px-2'
                  )
                }
              >
                <Icon className="w-5 h-5 flex-shrink-0" aria-hidden="true" />
                {!sidebarCollapsed && <span className="font-medium">{label}</span>}
              </NavLink>
            </motion.li>
          ))}
        </ul>
      </nav>

      {/* Collapse toggle */}
      <div className="p-2 border-t border-background-surface">
        <button
          onClick={toggleSidebar}
          className="w-full flex items-center justify-center p-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-background-surface transition-colors"
          aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-expanded={!sidebarCollapsed}
        >
          {sidebarCollapsed ? (
            <ChevronRight className="w-5 h-5" aria-hidden="true" />
          ) : (
            <>
              <ChevronLeft className="w-5 h-5" aria-hidden="true" />
              <span className="ml-2 text-sm">Collapse</span>
            </>
          )}
        </button>
      </div>
    </motion.aside>
  );
}
