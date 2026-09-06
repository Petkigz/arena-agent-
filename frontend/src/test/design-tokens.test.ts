/**
 * Design tokens (shared source of truth) — web side of the contract.
 *
 * design/tokens.json is the same file the desktop client reads via
 * desktop/design_tokens.py. These tests pin the web module's shape so a
 * malformed token file fails the frontend suite too, and verify the orb
 * component actually resolves its colors through the tokens.
 */
import { describe, expect, it } from 'vitest';
import rawTokens from '../../../design/tokens.json';
import {
  ACCENT,
  BEANIE_ORB_STATUSES,
  BEANIE_STATES,
  KNOWLEDGE_NODE_TYPE_COLORS,
  MEMORY_TYPE_COLORS,
  THEMES,
  beanieColor,
} from '../design/tokens';

const EXPECTED_STATES = [
  'idle',
  'working',
  'listening',
  'speaking',
  'offline',
  'thinking',
  'acting',
  'observing',
  'success',
  'error',
  'sleeping',
] as const;

describe('design tokens (shared source of truth)', () => {
  it('exposes exactly the 11 Beanie presence states', () => {
    expect([...BEANIE_ORB_STATUSES].sort()).toEqual([...EXPECTED_STATES].sort());
  });

  it('gives every state a 6-digit hex color and a non-negative duration', () => {
    for (const state of BEANIE_ORB_STATUSES) {
      const spec = BEANIE_STATES[state];
      expect(spec).toBeDefined();
      expect(spec.color).toMatch(/^#[0-9A-Fa-f]{6}$/);
      expect(spec.duration_ms).toBeGreaterThanOrEqual(0);
      expect(spec.label.length).toBeGreaterThan(0);
    }
  });

  it('beanieColor resolves every status and falls back to idle', () => {
    for (const state of BEANIE_ORB_STATUSES) {
      expect(beanieColor(state)).toBe(BEANIE_STATES[state].color);
    }
    expect(beanieColor('not-a-state')).toBe(BEANIE_STATES.idle.color);
  });

  it('exposes both theme palettes and the accent scale', () => {
    for (const theme of ['dark', 'light'] as const) {
      expect(THEMES[theme].background.primary).toMatch(/^#[0-9A-Fa-f]{6}$/);
      expect(THEMES[theme].text.secondary).toMatch(/^#[0-9A-Fa-f]{6}$/);
      expect(THEMES[theme].accent).toMatch(/^#[0-9A-Fa-f]{6}$/);
    }
    expect(ACCENT.primary).toBe('#3B82F6');
    expect(ACCENT.success).toBe('#10B981');
    expect(ACCENT.warning).toBe('#F59E0B');
    expect(ACCENT.error).toBe('#EF4444');
  });

  it('matches the raw token file (no transformation drift)', () => {
    expect(BEANIE_STATES).toEqual(rawTokens.beanie.states);
    expect(THEMES).toEqual(rawTokens.color.themes);
  });

  it('exposes the semantic taxonomies (node types, memory types) as hex palettes', () => {
    for (const key of ['concept', 'entity', 'memory', 'conversation', 'file', 'other']) {
      expect(KNOWLEDGE_NODE_TYPE_COLORS[key]).toMatch(/^#[0-9A-Fa-f]{6}$/);
    }
    for (const key of ['episodic', 'semantic', 'procedural', 'conversation', 'empty']) {
      expect(MEMORY_TYPE_COLORS[key]).toMatch(/^#[0-9A-Fa-f]{6}$/);
    }
  });
});
