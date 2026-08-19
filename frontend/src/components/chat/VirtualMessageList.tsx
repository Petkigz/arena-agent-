import { useRef } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import type { Message } from '../../types';
import { MessageBubble } from '../chat/MessageBubble';

interface VirtualMessageListProps {
  messages: Message[];
  onRetry?: (messageId: string) => void;
  onDelete?: (messageId: string) => void;
  className?: string;
}

export function VirtualMessageList({
  messages,
  onRetry,
  onDelete,
  className = '',
}: VirtualMessageListProps) {
  const parentRef = useRef<HTMLDivElement>(null);

  // Use virtualizer for efficient rendering of large message lists
  const virtualizer = useVirtualizer({
    count: messages.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 120, // Estimated height of each message
    overscan: 5, // Render 5 extra items above and below viewport
    getItemKey: (index) => messages[index].id,
  });

  const virtualItems = virtualizer.getVirtualItems();

  return (
    <div
      ref={parentRef}
      className={`flex-1 overflow-y-auto px-4 py-4 ${className}`}
      style={{ contain: 'strict' }}
    >
      <div
        style={{
          height: virtualizer.getTotalSize(),
          width: '100%',
          position: 'relative',
        }}
      >
        {virtualItems.map((virtualItem) => {
          const message = messages[virtualItem.index];
          return (
            <div
              key={message.id}
              data-index={virtualItem.index}
              ref={virtualizer.measureElement}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                transform: `translateY(${virtualItem.start}px)`,
              }}
              className="mb-4"
            >
              <MessageBubble
                message={message}
                onRetry={onRetry}
                onDelete={onDelete}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}
