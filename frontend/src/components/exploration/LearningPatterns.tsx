import { useMemo } from 'react';
import { Card } from '../ui';
import type { Memory } from '../../stores/memoryBrowserStore';
import type { Conversation } from '../../types';
import type { KnowledgeNode } from '../../stores/knowledgeGraphStore';
import { TrendingUp, Brain, Database, MessageCircle, Star, Calendar, Tag } from 'lucide-react';
import { format, subDays, differenceInDays } from 'date-fns';
import { MEMORY_TYPE_COLORS } from '../../design/tokens';

interface LearningPatternsProps {
  memories: Memory[];
  conversations: Conversation[];
  knowledgeNodes: KnowledgeNode[];
}

interface DailyActivity {
  date: string;
  memories: number;
  conversations: number;
  knowledge: number;
}

interface CategoryStats {
  category: string;
  count: number;
  avgImportance: number;
  icon: string;
  color: string;
}

export function LearningPatterns({ memories, conversations, knowledgeNodes }: LearningPatternsProps) {
  // Calculate daily activity for the last 30 days
  const dailyActivity = useMemo(() => {
    const days: DailyActivity[] = [];
    const today = new Date();

    for (let i = 29; i >= 0; i--) {
      const date = subDays(today, i);
      const dateStr = format(date, 'yyyy-MM-dd');

      const dayMemories = memories.filter(
        (m) => m.metadata.createdAt.startsWith(dateStr)
      ).length;
      const dayConversations = conversations.filter(
        (c) => c.createdAt.startsWith(dateStr)
      ).length;
      const dayKnowledge = knowledgeNodes.filter(
        (n) => n.metadata.createdAt.startsWith(dateStr)
      ).length;

      days.push({
        date: dateStr,
        memories: dayMemories,
        conversations: dayConversations,
        knowledge: dayKnowledge,
      });
    }

    return days;
  }, [memories, conversations, knowledgeNodes]);

  // Calculate category stats
  const categoryStats = useMemo((): CategoryStats[] => {
    const categories = ['episodic', 'semantic', 'procedural', 'conversation'] as const;
    const icons: Record<string, string> = {
      episodic: '🎭',
      semantic: '🧠',
      procedural: '⚙️',
      conversation: '💬',
    };
    // Memory-type colors come from the shared design system (design/tokens.json).
    const colors: Record<string, string> = MEMORY_TYPE_COLORS;

    return categories.map((cat) => {
      const catMemories = memories.filter((m) => m.category === cat);
      const avgImportance =
        catMemories.length > 0
          ? catMemories.reduce((sum, m) => sum + m.metadata.importance, 0) / catMemories.length
          : 0;

      return {
        category: cat,
        count: catMemories.length,
        avgImportance: Math.round(avgImportance * 10) / 10,
        icon: icons[cat],
        color: colors[cat],
      };
    });
  }, [memories]);

  // Calculate top tags
  const topTags = useMemo(() => {
    const tagCounts = new Map<string, number>();
    for (const memory of memories) {
      for (const tag of memory.metadata.tags) {
        tagCounts.set(tag, (tagCounts.get(tag) || 0) + 1);
      }
    }
    return Array.from(tagCounts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10);
  }, [memories]);

  // Calculate streak
  const streak = useMemo(() => {
    const today = new Date();
    let currentStreak = 0;

    for (let i = 0; i < 365; i++) {
      const date = subDays(today, i);
      const dateStr = format(date, 'yyyy-MM-dd');

      const hasActivity =
        memories.some((m) => m.metadata.createdAt.startsWith(dateStr)) ||
        conversations.some((c) => c.createdAt.startsWith(dateStr));

      if (hasActivity) {
        currentStreak++;
      } else if (i > 0) {
        break;
      }
    }

    return currentStreak;
  }, [memories, conversations]);

  // Learning velocity (items per day over last 7 days)
  const velocity = useMemo(() => {
    const sevenDaysAgo = subDays(new Date(), 7);
    const recentMemories = memories.filter(
      (m) => new Date(m.metadata.createdAt) >= sevenDaysAgo
    );
    return Math.round((recentMemories.length / 7) * 10) / 10;
  }, [memories]);

  // Max activity for chart scaling
  const maxActivity = useMemo(() => {
    return Math.max(
      1,
      ...dailyActivity.map((d) => d.memories + d.conversations + d.knowledge)
    );
  }, [dailyActivity]);

  const totalItems = memories.length + conversations.length + knowledgeNodes.length;
  const daysSinceStart = useMemo(() => {
    const allDates = [
      ...memories.map((m) => new Date(m.metadata.createdAt)),
      ...conversations.map((c) => new Date(c.createdAt)),
      ...knowledgeNodes.map((n) => new Date(n.metadata.createdAt)),
    ];
    if (allDates.length === 0) return 1;
    const earliest = new Date(Math.min(...allDates.map((d) => d.getTime())));
    return Math.max(1, differenceInDays(new Date(), earliest));
  }, [memories, conversations, knowledgeNodes]);

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="p-4">
          <div className="flex items-center gap-2 text-text-muted mb-1">
            <Database className="w-4 h-4" />
            <span className="text-sm">Total Items</span>
          </div>
          <p className="text-2xl font-bold text-text-primary">{totalItems}</p>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-2 text-text-muted mb-1">
            <TrendingUp className="w-4 h-4" />
            <span className="text-sm">Daily Velocity</span>
          </div>
          <p className="text-2xl font-bold text-text-primary">{velocity}</p>
          <p className="text-xs text-text-muted">items/day (7d avg)</p>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-2 text-text-muted mb-1">
            <Star className="w-4 h-4" />
            <span className="text-sm">Active Streak</span>
          </div>
          <p className="text-2xl font-bold text-text-primary">{streak}</p>
          <p className="text-xs text-text-muted">days</p>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-2 text-text-muted mb-1">
            <Calendar className="w-4 h-4" />
            <span className="text-sm">Days Active</span>
          </div>
          <p className="text-2xl font-bold text-text-primary">{daysSinceStart}</p>
        </Card>
      </div>

      {/* Activity Chart */}
      <Card className="p-4">
        <h3 className="text-lg font-semibold text-text-primary mb-4">
          30-Day Activity
        </h3>
        <div className="flex items-end gap-1 h-32">
          {dailyActivity.map((day) => {
            const total = day.memories + day.conversations + day.knowledge;
            const height = (total / maxActivity) * 100;
            return (
              <div
                key={day.date}
                className="flex-1 flex flex-col justify-end group relative"
              >
                <div
                  className="w-full rounded-t transition-all"
                  style={{
                    height: `${Math.max(height, total > 0 ? 4 : 0)}%`,
                    backgroundColor: total > 0 ? MEMORY_TYPE_COLORS.episodic : MEMORY_TYPE_COLORS.empty,
                    opacity: total > 0 ? 0.6 + (total / maxActivity) * 0.4 : 0.3,
                  }}
                />
                {/* Tooltip */}
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 hidden group-hover:block z-20">
                  <div className="bg-background-surface border border-border rounded px-2 py-1 text-xs text-text-primary whitespace-nowrap shadow-lg">
                    <div className="font-medium">{format(new Date(day.date), 'MMM d')}</div>
                    {day.memories > 0 && <div>Memories: {day.memories}</div>}
                    {day.conversations > 0 && <div>Conversations: {day.conversations}</div>}
                    {day.knowledge > 0 && <div>Knowledge: {day.knowledge}</div>}
                    {total === 0 && <div>No activity</div>}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
        <div className="flex justify-between text-xs text-text-muted mt-2">
          <span>{format(new Date(dailyActivity[0]?.date || ''), 'MMM d')}</span>
          <span>Today</span>
        </div>
      </Card>

      {/* Category Distribution */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card className="p-4">
          <h3 className="text-lg font-semibold text-text-primary mb-4">
            Memory Categories
          </h3>
          <div className="space-y-3">
            {categoryStats.map((stat) => (
              <div key={stat.category} className="flex items-center gap-3">
                <span className="text-lg">{stat.icon}</span>
                <div className="flex-1">
                  <div className="flex justify-between items-center mb-1">
                    <span className="text-sm font-medium text-text-primary capitalize">
                      {stat.category}
                    </span>
                    <span className="text-sm text-text-muted">{stat.count}</span>
                  </div>
                  <div className="h-2 bg-background-surface rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{
                        width: `${memories.length > 0 ? (stat.count / memories.length) * 100 : 0}%`,
                        backgroundColor: stat.color,
                      }}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card className="p-4">
          <h3 className="text-lg font-semibold text-text-primary mb-4">
            Knowledge Breakdown
          </h3>
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <Brain className="w-5 h-5 text-purple-500" />
              <div className="flex-1">
                <div className="flex justify-between items-center">
                  <span className="text-sm font-medium text-text-primary">Knowledge Nodes</span>
                  <span className="text-sm text-text-muted">{knowledgeNodes.length}</span>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <MessageCircle className="w-5 h-5 text-amber-500" />
              <div className="flex-1">
                <div className="flex justify-between items-center">
                  <span className="text-sm font-medium text-text-primary">Conversations</span>
                  <span className="text-sm text-text-muted">{conversations.length}</span>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Database className="w-5 h-5 text-blue-500" />
              <div className="flex-1">
                <div className="flex justify-between items-center">
                  <span className="text-sm font-medium text-text-primary">Memories</span>
                  <span className="text-sm text-text-muted">{memories.length}</span>
                </div>
              </div>
            </div>
          </div>

          {topTags.length > 0 && (
            <>
              <h4 className="text-sm font-semibold text-text-primary mt-6 mb-3 flex items-center gap-1">
                <Tag className="w-4 h-4" />
                Top Tags
              </h4>
              <div className="flex flex-wrap gap-2">
                {topTags.map(([tag, count]) => (
                  <span
                    key={tag}
                    className="px-2 py-1 bg-background-surface text-text-secondary text-xs rounded-lg"
                  >
                    #{tag} <span className="text-text-muted">({count})</span>
                  </span>
                ))}
              </div>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
