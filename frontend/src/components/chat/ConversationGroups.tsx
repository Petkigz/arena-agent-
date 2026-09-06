import { memo } from 'react';
import type { Conversation } from '../../types';
import { groupConversationsByDate } from '../../utils/conversationGroups';
import { ConversationItem } from './ConversationItem';

interface ConversationGroupsProps {
  conversations: Conversation[];
  currentId?: string | null;
  onSelect: (id: string) => void;
  onDelete: (e: React.MouseEvent, id: string) => void;
}

/**
 * Conversation history as the primary navigation experience — grouped by
 * recency (Today / Yesterday / Previous 7 days / Older), matching the
 * reference's information architecture.
 */
function ConversationGroupsComponent({
  conversations,
  currentId,
  onSelect,
  onDelete,
}: ConversationGroupsProps) {
  const groups = groupConversationsByDate(conversations);

  return (
    <nav aria-label="Conversation history">
      {groups.map((group) => (
        <section key={group.key} aria-label={group.label} className="mb-3">
          <h3 className="px-3 py-1 text-xs font-medium text-text-muted uppercase tracking-wider">
            {group.label}
          </h3>
          <ul className="list-none p-0 m-0" role="list">
            {group.conversations.map((conversation) => (
              <li key={conversation.id} role="listitem">
                <ConversationItem
                  conversation={conversation}
                  isActive={currentId === conversation.id}
                  onSelect={onSelect}
                  onDelete={onDelete}
                />
              </li>
            ))}
          </ul>
        </section>
      ))}
    </nav>
  );
}

export const ConversationGroups = memo(ConversationGroupsComponent);
