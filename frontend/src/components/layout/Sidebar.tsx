import { useEffect, useState, useCallback, useMemo } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { Brain, Settings, Plus, File, Code, Image, ChevronLeft, ChevronRight } from 'lucide-react';
import { motion } from 'framer-motion';
import { cn } from '../../utils/cn';
import { Button } from '../ui/Button';
import { ConversationFilters } from '../chat/ConversationFilters';
import { ConversationGroups } from '../chat/ConversationGroups';
import { BEANIE_STATES } from '../../design/tokens';
import { useConversationStore, useLayoutStore, usePresenceStore } from '../../stores';
import { webSocketService } from '../../services/websocket';
import { ReactiveBeanieOrb } from '../presence/ReactiveBeanieOrb';

type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'reconnecting';

const statusConfig: Record<ConnectionStatus, { color: string; label: string }> = {
  connected: { color: 'bg-accent-success', label: 'Online' },
  connecting: { color: 'bg-accent-warning', label: 'Connecting...' },
  reconnecting: { color: 'bg-accent-warning', label: 'Reconnecting...' },
  disconnected: { color: 'bg-accent-error', label: 'Offline' },
};

export function Sidebar() {
  const navigate = useNavigate();
  const { conversations, currentConversation, createConversation, setCurrentConversation, removeConversation } =
    useConversationStore();
  const { sidebarCollapsed, toggleSidebar } = useLayoutStore();
  const { presence } = usePresenceStore();

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

  // The tool nav below the history divider (21s reference IA). 'Chats' is not
  // here on purpose: the conversation history IS the chat navigation.
  const links = useMemo(() => [
    { to: '/pansophy', icon: Brain, label: 'Pansophy' },
    { to: '/images', icon: Image, label: 'Images' },
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
        'bg-background-secondary border-r border-border-subtle flex flex-col transition-all duration-300',
        sidebarCollapsed ? 'w-16' : 'w-64'
      )}
    >
      {/* Brand + Beanie presence orb with real connection status */}
      <div className="p-4 border-b border-border-subtle" data-tutorial="presence-orb">
        {!sidebarCollapsed && (
          <p className="text-xs font-semibold text-text-muted uppercase tracking-[0.25em] mb-3">Arena</p>
        )}
        <div className="flex items-center gap-3">
          <ReactiveBeanieOrb
            status={connectionStatus === 'disconnected' ? 'offline' : presence.status}
            size="sm"
          />
          {!sidebarCollapsed && (
            <div className="flex-1 min-w-0">
              <h2 className="font-semibold bg-beanie-gradient bg-clip-text text-transparent">Beanie</h2>
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
          aria-label={sidebarCollapsed ? 'New chat' : undefined}
        >
          <Plus className="w-4 h-4" aria-hidden="true" />
          {!sidebarCollapsed && <span className="ml-2">New Chat</span>}
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

      {/* Conversation history — the primary navigation experience (21s) */}
      {!sidebarCollapsed && (
        <div className="flex-1 overflow-y-auto px-2 py-2" data-tutorial="conversation-list" role="region" aria-label="Conversation history">
          {conversations.length > 0 ? (
            <ConversationGroups
              conversations={conversations}
              currentId={currentConversation?.id}
              onSelect={handleSelectConversation}
              onDelete={handleDeleteConversation}
            />
          ) : (
            <p className="px-3 py-6 text-sm text-text-muted" role="status">
              No conversations yet — start one above.
            </p>
          )}
        </div>
      )}

      {/* Tool navigation — compact, below the history divider */}
      <nav
        className={cn('px-2 pt-2 border-t border-border-subtle', sidebarCollapsed && 'px-1')}
        aria-label="Main navigation"
      >
        <ul className="list-none p-0 m-0" role="list">
          {links.map(({ to, icon: Icon, label }) => (
            <motion.li
              key={to}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.2 }}
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

      {/* Beanie presence card */}
      {!sidebarCollapsed && (
        <div
          className="mx-2 mb-2 p-3 rounded-xl bg-background-panel border border-border-subtle flex items-center gap-3"
          role="status"
          aria-label="Beanie presence"
        >
          <ReactiveBeanieOrb
            status={connectionStatus === 'disconnected' ? 'offline' : presence.status}
            size="sm"
          />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-text-primary">
              {BEANIE_STATES[presence.status]?.label ?? 'Idle'}
            </p>
            <p className="text-xs text-text-muted truncate">{presence.message}</p>
          </div>
        </div>
      )}

      {/* Collapse toggle */}
      <div className="p-2 border-t border-border-subtle">
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
