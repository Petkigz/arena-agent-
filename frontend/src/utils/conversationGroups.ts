import type { Conversation } from '../types';

/**
 * Conversation history groups — the sidebar's primary navigation (21s review:
 * the reference makes conversation history a navigation experience, not a
 * flat capped list).
 */

export type ConversationGroupKey = 'today' | 'yesterday' | 'previous-7-days' | 'older';

export interface ConversationGroup {
  key: ConversationGroupKey;
  label: string;
  conversations: Conversation[];
}

const GROUP_ORDER: ConversationGroupKey[] = ['today', 'yesterday', 'previous-7-days', 'older'];

const GROUP_LABELS: Record<ConversationGroupKey, string> = {
  today: 'Today',
  yesterday: 'Yesterday',
  'previous-7-days': 'Previous 7 days',
  older: 'Older',
};

/** Local-calendar-day difference between a date and "now". */
function dayDiff(updatedAt: string, now: Date): number | null {
  const then = new Date(updatedAt);
  if (Number.isNaN(then.getTime())) {
    return null;
  }
  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const MS_PER_DAY = 86_400_000;
  return Math.round((startOfDay(now) - startOfDay(then)) / MS_PER_DAY);
}

function bucketFor(diff: number | null): ConversationGroupKey {
  if (diff === null || diff < 0) return 'older'; // unknown or future dates: don't invent a group
  if (diff === 0) return 'today';
  if (diff === 1) return 'yesterday';
  if (diff <= 8) return 'previous-7-days'; // the 7 calendar days before yesterday
  return 'older';
}

/**
 * Bucket conversations by recency (Today / Yesterday / Previous 7 days /
 * Older), newest first within each bucket, empty buckets omitted.
 */
export function groupConversationsByDate(
  conversations: Conversation[],
  now: Date = new Date(),
): ConversationGroup[] {
  const buckets = new Map<ConversationGroupKey, Conversation[]>();
  for (const key of GROUP_ORDER) buckets.set(key, []);

  for (const conversation of conversations) {
    buckets.get(bucketFor(dayDiff(conversation.updatedAt, now)))!.push(conversation);
  }

  return GROUP_ORDER
    .filter((key) => buckets.get(key)!.length > 0)
    .map((key) => ({
      key,
      label: GROUP_LABELS[key],
      conversations: [...buckets.get(key)!].sort(
        (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
      ),
    }));
}
