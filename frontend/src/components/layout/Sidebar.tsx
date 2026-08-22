import { useEffect, useState, useCallback, useMemo } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { MessageCircle, Brain, Settings, Plus, File, Code, ChevronLeft, ChevronRight, Sparkles } from 'lucide-react';
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
  const { conversations, currentConversation, createConversation, setCurrentConversation, removeConversation } = useConversationStore();
  const { sidebarCollapsed, toggleSidebar } = useLayoutStore();
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>(webSocketService.status);
  const [showFilters, setShowFilters] = useState(false);

  useEffect(() => webSocketService.onStatusChange((status) => setConnectionStatus(status)), []);

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

  const status = statusConfig[connectionStatus];

  return (
    <motion.aside
      initial={{ x: -20, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      aria-label="Application sidebar"
      className={cn('bg-background-secondary border-r border-background-surface flex flex-col transition-all duration-300', sidebarCollapsed ? 'w-16' : 'w-64')}
    >
      <div className="p-4 border-b border-background-surface" data-tutorial="presence-orb">
        <NavLink to="/beanie" className="flex items-center gap-3 group" aria-label="Open Beanie">
          <div className="relative w-10 h-10 flex-shrink-0 rounded-full bg-gradient-to-br from-blue-400/80 via-blue-600 to-slate-950 shadow-[0_0_20px_rgba(59,130,246,.28)] flex items-center justify-center">
            <span className="w-1.5 h-1.5 rounded-full bg-white shadow-[0_0_10px_rgba(255,255,255,.9)]" />
          </div>
          {!sidebarCollapsed && (
            <div className="flex-1 min-w-0">
              <h2 className="font-semibold text-text-primary group-hover:text-accent-primary transition-colors">Beanie</h2>
              <div className="flex items-center gap-1.5" role="status" aria-live="polite" aria-atomic="true">
                <span className={`w-2 h-2 rounded-full ${status.color}`} aria-hidden="true" />
                <p className="text-xs text-text-muted">Personal AI · {status.label}</p>
              </div>
            </div>
          )}
          {sidebarCollapsed && <span className="sr-only">Beanie — {status.label}</span>}
        </NavLink>
      </div>

      <div className={cn('p-4 space-y-3', sidebarCollapsed && 'px-2')}>
        <Button className={cn('w-full', sidebarCollapsed && 'px-2')} variant="primary" onClick={handleNewConversation} aria-label={sidebarCollapsed ? 'New conversation' : undefined}>
          <Plus className="w-4 h-4" aria-hidden="true" />
          {!sidebarCollapsed && <span className="ml-2">New Conversation</span>}
        </Button>

        {!sidebarCollapsed && conversations.length > 0 && (
          <button onClick={() => setShowFilters(!showFilters)} className="w-full text-sm text-text-muted hover:text-text-primary transition-colors" aria-expanded={showFilters} aria-controls="conversation-filters">
            {showFilters ? 'Hide Filters' : 'Show Filters'}
          </button>
        )}
        {showFilters && !sidebarCollapsed && <div id="conversation-filters"><ConversationFilters /></div>}
      </div>

      {!sidebarCollapsed && conversations.length > 0 && (
        <div className="px-2 mb-2" data-tutorial="conversation-list" role="region" aria-label="Conversations">
          <h3 className="px-3 text-xs font-medium text-text-muted uppercase tracking-wide mb-1">Conversations</h3>
          <ul className="space-y-0.5 max-h-48 overflow-y-auto">
            <AnimatePresence>
              {conversations.map((conv) => (
                <li key={conv.id}>
                  <ConversationItem conversation={conv} isActive={currentConversation?.id === conv.id} onSelect={handleSelectConversation} onDelete={handleDeleteConversation} />
                </li>
              ))}
            </AnimatePresence>
          </ul>
        </div>
      )}

      <nav className={cn('flex-1 overflow-y-auto px-2', sidebarCollapsed && 'px-1')} aria-label="Main navigation">
        <ul className="list-none p-0 m-0">
          <li>
            <NavLink to="/beanie" className={({ isActive }) => cn('flex items-center gap-3 px-3 py-2 rounded-lg mb-1 transition-colors', isActive ? 'bg-accent-primary text-white' : 'text-text-secondary hover:bg-background-surface hover:text-text-primary', sidebarCollapsed && 'justify-center px-2')}>
              <Sparkles className="w-5 h-5 flex-shrink-0" aria-hidden="true" />
              {!sidebarCollapsed && <span className="font-medium">Beanie</span>}
            </NavLink>
          </li>
          {links.map(({ to, icon: Icon, label }, index) => (
            <motion.li key={to} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.2, delay: index * 0.05 }}>
              <NavLink to={to} data-tutorial={`nav-${label.toLowerCase()}`} aria-label={sidebarCollapsed ? label : undefined} className={({ isActive }) => cn('flex items-center gap-3 px-3 py-2 rounded-lg mb-1 transition-colors', isActive ? 'bg-accent-primary text-white' : 'text-text-secondary hover:bg-background-surface hover:text-text-primary', sidebarCollapsed && 'justify-center px-2')}>
                <Icon className="w-5 h-5 flex-shrink-0" aria-hidden="true" />
                {!sidebarCollapsed && <span className="font-medium">{label}</span>}
              </NavLink>
            </motion.li>
          ))}
        </ul>
      </nav>

      <div className="p-2 border-t border-background-surface">
        <button onClick={toggleSidebar} className="w-full flex items-center justify-center p-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-background-surface transition-colors" aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'} aria-expanded={!sidebarCollapsed}>
          {sidebarCollapsed ? <ChevronRight className="w-5 h-5" aria-hidden="true" /> : <><ChevronLeft className="w-5 h-5" aria-hidden="true" /><span className="ml-2 text-sm">Collapse</span></>}
        </button>
      </div>
    </motion.aside>
  );
}
