import { describe, it, expect } from 'vitest';
import { groupConversationsByDate } from '../../utils/conversationGroups';
import type { Conversation } from '../../types';

const NOW = new Date('2026-09-06T15:00:00');

function conv(id: string, updatedAt: string): Conversation {
  return {
    id,
    title: id,
    messages: [],
    createdAt: updatedAt,
    updatedAt,
  };
}

function hoursAgo(hours: number): string {
  return new Date(NOW.getTime() - hours * 3_600_000).toISOString();
}

describe('groupConversationsByDate', () => {
  it('buckets by calendar day: today, yesterday, previous 7 days, older', () => {
    const groups = groupConversationsByDate(
      [
        conv('today-morning', hoursAgo(2)),
        conv('today-midnight', '2026-09-06T00:30:00'),
        conv('yesterday', '2026-09-05T18:00:00'),
        conv('day-2', '2026-09-04T12:00:00'),
        conv('day-8', '2026-08-29T12:00:00'),
        conv('older', '2026-08-20T12:00:00'),
      ],
      NOW,
    );

    expect(groups.map((g) => g.key)).toEqual(['today', 'yesterday', 'previous-7-days', 'older']);
    expect(groups[0].conversations.map((c) => c.id)).toEqual(['today-morning', 'today-midnight']);
    expect(groups[1].conversations.map((c) => c.id)).toEqual(['yesterday']);
    expect(groups[2].conversations.map((c) => c.id)).toEqual(['day-2', 'day-8']);
    expect(groups[3].conversations.map((c) => c.id)).toEqual(['older']);
  });

  it('uses local calendar days, not 24-hour windows', () => {
    // 26 hours before NOW is 2026-09-05 13:00 — yesterday, not today
    const groups = groupConversationsByDate([conv('edge', hoursAgo(26))], NOW);
    expect(groups[0].key).toBe('yesterday');
  });

  it('day 8 after yesterday is still previous-7-days; day 9 is older', () => {
    const groups = groupConversationsByDate(
      [conv('d8', '2026-08-29T23:00:00'), conv('d9', '2026-08-28T01:00:00')],
      NOW,
    );
    expect(groups[0].key).toBe('previous-7-days');
    expect(groups[0].conversations.map((c) => c.id)).toEqual(['d8']);
    expect(groups[1].key).toBe('older');
    expect(groups[1].conversations.map((c) => c.id)).toEqual(['d9']);
  });

  it('sorts newest-first within each group', () => {
    const groups = groupConversationsByDate(
      [conv('old-first', hoursAgo(10)), conv('new-first', hoursAgo(1))],
      NOW,
    );
    expect(groups[0].conversations.map((c) => c.id)).toEqual(['new-first', 'old-first']);
  });

  it('omits empty groups entirely', () => {
    const groups = groupConversationsByDate([conv('only-today', hoursAgo(1))], NOW);
    expect(groups).toHaveLength(1);
    expect(groups[0].label).toBe('Today');
  });

  it('returns nothing for an empty history', () => {
    expect(groupConversationsByDate([], NOW)).toEqual([]);
  });

  it('puts unparseable timestamps in Older rather than crashing', () => {
    const groups = groupConversationsByDate([conv('broken', 'not-a-date')], NOW);
    expect(groups[0].key).toBe('older');
  });

  it('labels groups for humans', () => {
    const labels = groupConversationsByDate(
      [conv('a', hoursAgo(1)), conv('b', hoursAgo(30)), conv('c', hoursAgo(24 * 3)), conv('d', hoursAgo(24 * 40))],
      NOW,
    ).map((g) => g.label);
    expect(labels).toEqual(['Today', 'Yesterday', 'Previous 7 days', 'Older']);
  });
});
