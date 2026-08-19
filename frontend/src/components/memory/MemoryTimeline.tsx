import { useMemo } from 'react';
import { Card } from '../ui';
import type { Memory } from '../../stores/memoryBrowserStore';
import { format, isToday, isYesterday, isThisWeek, isThisMonth } from 'date-fns';
import { Calendar, Star, MessageCircle } from 'lucide-react';
import { highlightText } from '../../utils/searchHighlight';

interface MemoryTimelineProps {
  memories: Memory[];
  searchQuery?: string;
  onConversationClick?: (conversationId: string) => void;
}

interface TimelineGroup {
  label: string;
  date: string;
  memories: Memory[];
}

const categoryColors: Record<string, string> = {
  episodic: 'border-purple-400 bg-purple-50',
  semantic: 'border-blue-400 bg-blue-50',
  procedural: 'border-green-400 bg-green-50',
  conversation: 'border-amber-400 bg-amber-50',
};

const categoryIcons: Record<string, string> = {
  episodic: '🎭',
  semantic: '🧠',
  procedural: '⚙️',
  conversation: '💬',
};

export function MemoryTimeline({ memories, searchQuery = '', onConversationClick }: MemoryTimelineProps) {
  const groups = useMemo(() => {
    const sorted = [...memories].sort(
      (a, b) => new Date(b.metadata.createdAt).getTime() - new Date(a.metadata.createdAt).getTime()
    );

    const groupMap = new Map<string, Memory[]>();

    for (const memory of sorted) {
      const date = new Date(memory.metadata.createdAt);
      let key: string;

      if (isToday(date)) {
        key = 'today';
      } else if (isYesterday(date)) {
        key = 'yesterday';
      } else if (isThisWeek(date)) {
        key = 'this-week';
      } else if (isThisMonth(date)) {
        key = 'this-month';
      } else {
        key = format(date, 'yyyy-MM');
      }

      if (!groupMap.has(key)) {
        groupMap.set(key, []);
      }
      groupMap.get(key)!.push(memory);
    }

    const result: TimelineGroup[] = [];
    const orderedKeys = ['today', 'yesterday', 'this-week', 'this-month'];
    const labelMap: Record<string, string> = {
      today: 'Today',
      yesterday: 'Yesterday',
      'this-week': 'This Week',
      'this-month': 'This Month',
    };

    // Add ordered groups first
    for (const key of orderedKeys) {
      const mems = groupMap.get(key);
      if (mems) {
        result.push({ label: labelMap[key], date: key, memories: mems });
        groupMap.delete(key);
      }
    }

    // Add remaining groups sorted by date
    const remaining = Array.from(groupMap.entries()).sort((a, b) => b[0].localeCompare(a[0]));
    for (const [key, mems] of remaining) {
      const label = key.startsWith('2')
        ? format(new Date(key + '-01'), 'MMMM yyyy')
        : key;
      result.push({ label, date: key, memories: mems });
    }

    return result;
  }, [memories]);

  if (memories.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <Card className="max-w-md">
          <div className="text-center">
            <Calendar className="w-16 h-16 text-text-muted mx-auto mb-4" />
            <h3 className="text-xl font-semibold text-text-primary mb-2">
              No Memories in Timeline
            </h3>
            <p className="text-text-secondary">
              Memories will appear here chronologically as they are created.
            </p>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {groups.map((group) => (
        <div key={group.date}>
          <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wide mb-3 sticky top-0 bg-background-primary py-1 z-10">
            {group.label}
          </h3>
          <div className="relative pl-6 border-l-2 border-border space-y-3">
            {group.memories.map((memory) => (
              <div key={memory.id} className="relative">
                {/* Timeline dot */}
                <div className="absolute -left-[25px] top-3 w-3 h-3 rounded-full bg-accent-primary border-2 border-background-primary" />

                <Card className={`border-l-4 ${categoryColors[memory.category]} p-3`}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-sm">{categoryIcons[memory.category]}</span>
                        <span className="text-xs font-medium text-text-muted uppercase">
                          {memory.category}
                        </span>
                        <span className="text-xs text-text-muted">
                          {format(new Date(memory.metadata.createdAt), 'h:mm a')}
                        </span>
                      </div>
                      <h4 className="font-medium text-text-primary">
                        {highlightText(memory.title, searchQuery)}
                      </h4>
                      <p className="text-sm text-text-secondary mt-1 line-clamp-2">
                        {highlightText(memory.content, searchQuery)}
                      </p>
                      {memory.metadata.tags.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-2">
                          {memory.metadata.tags.map((tag) => (
                            <span
                              key={tag}
                              className="px-1.5 py-0.5 bg-background-surface text-text-muted text-xs rounded"
                            >
                              #{tag}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="flex flex-col items-end gap-1 flex-shrink-0">
                      <div className="flex items-center gap-1 text-xs text-text-muted">
                        <Star className="w-3 h-3" />
                        <span>{memory.metadata.importance}</span>
                      </div>
                      {memory.metadata.conversationId && (
                        <button
                          onClick={() => onConversationClick?.(memory.metadata.conversationId!)}
                          className="flex items-center gap-1 text-xs text-accent-primary hover:underline"
                        >
                          <MessageCircle className="w-3 h-3" />
                          <span>View</span>
                        </button>
                      )}
                    </div>
                  </div>
                </Card>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
