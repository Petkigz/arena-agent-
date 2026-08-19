import { memo, useCallback, useMemo } from 'react';
import { MessageCircle, Trash2 } from 'lucide-react';
import { motion } from 'framer-motion';
import { cn } from '../../utils/cn';
import { formatDistanceToNow } from 'date-fns';
import type { Conversation } from '../../types';

interface ConversationItemProps {
  conversation: Conversation;
  isActive: boolean;
  onSelect: (id: string) => void;
  onDelete: (e: React.MouseEvent, id: string) => void;
}

function ConversationItemComponent({
  conversation,
  isActive,
  onSelect,
  onDelete,
}: ConversationItemProps) {
  const handleClick = useCallback(() => {
    onSelect(conversation.id);
  }, [onSelect, conversation.id]);

  const handleDelete = useCallback((e: React.MouseEvent) => {
    onDelete(e, conversation.id);
  }, [onDelete, conversation.id]);

  // Memoize relative time formatting
  const relativeTime = useMemo(() => {
    return formatDistanceToNow(new Date(conversation.updatedAt), { addSuffix: true });
  }, [conversation.updatedAt]);

  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -10 }}
      transition={{ duration: 0.2 }}
      onClick={handleClick}
      className={cn(
        'group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors',
        isActive
          ? 'bg-accent-primary/20 text-text-primary'
          : 'text-text-secondary hover:bg-background-surface hover:text-text-primary'
      )}
    >
      <MessageCircle className="w-4 h-4 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{conversation.title}</p>
        <p className="text-xs text-text-muted truncate">
          {relativeTime}
        </p>
      </div>
      <button
        onClick={handleDelete}
        className="opacity-0 group-hover:opacity-100 p-1 text-text-muted hover:text-accent-error transition-all"
      >
        <Trash2 className="w-3 h-3" />
      </button>
    </motion.div>
  );
}

// Custom comparison function for React.memo
function arePropsEqual(prevProps: ConversationItemProps, nextProps: ConversationItemProps): boolean {
  return (
    prevProps.conversation.id === nextProps.conversation.id &&
    prevProps.conversation.title === nextProps.conversation.title &&
    prevProps.conversation.updatedAt === nextProps.conversation.updatedAt &&
    prevProps.isActive === nextProps.isActive &&
    prevProps.onSelect === nextProps.onSelect &&
    prevProps.onDelete === nextProps.onDelete
  );
}

export const ConversationItem = memo(ConversationItemComponent, arePropsEqual);
