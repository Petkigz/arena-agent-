/**
 * Design tokens — programmatic access to the shared design system.
 *
 * The canonical source is design/tokens.json at the repo root — the SAME
 * file the desktop client reads (desktop/design_tokens.py). This module is
 * the web client's only sanctioned entry point to it: import colors and the
 * Beanie presence palette from here, never hardcode hex values in
 * components, configs or stylesheets.
 *
 * Enforced by tests/test_design_tokens.py (cross-client agreement) and
 * frontend/src/test/design-tokens.test.ts (this module's shape).
 */
import tokens from '../../../design/tokens.json';

export interface BeanieStateSpec {
  label: string;
  color: string;
  duration_ms: number;
}

export interface ThemePalette {
  background: {
    primary: string;
    secondary: string;
    surface: string;
    panel: string;
    elevated: string;
    panel_alpha: number;
  };
  text: { primary: string; secondary: string; muted: string };
  accent: string;
  border: { subtle: string; active: string };
  /** Beanie's glow — light emitted by the presence states (atmosphere). */
  glow: { primary: string; secondary: string };
}

/** All 11 Beanie presence states, keyed by state name. */
export const BEANIE_STATES: Record<string, BeanieStateSpec> = tokens.beanie.states;

/** The Beanie presence state names, derived from the token file. */
export type BeanieOrbStatus = keyof typeof tokens.beanie.states;

export const BEANIE_ORB_STATUSES = Object.keys(BEANIE_STATES) as BeanieOrbStatus[];

/** Semantic accent scale (same in both themes). */
export const ACCENT: Record<string, string> = tokens.color.accent;

/** Knowledge-graph node taxonomy colors (theme-independent, like presence). */
export const KNOWLEDGE_NODE_TYPE_COLORS: Record<string, string> = tokens.color.knowledge_node_types;

/** Memory-type taxonomy colors (theme-independent). */
export const MEMORY_TYPE_COLORS: Record<string, string> = tokens.color.memory_types;

/** Theme palettes (dark is the default). */
export const THEMES: Record<'dark' | 'light', ThemePalette> = tokens.color.themes;

/** Resolve a state to its canonical color; unknown states fall back to idle. */
export function beanieColor(status: string): string {
  return BEANIE_STATES[status]?.color ?? BEANIE_STATES.idle.color;
}

/** Base typography tokens (see index.css --arena-font-* variables). */
export const FONT_FAMILY: string = tokens.typography.font_family;
export const BASE_FONT_SIZE_PX: number = tokens.typography.base_font_size_px;

/** Type scale (px) — caption/body/subtitle/title/display. */
export const TYPE_SCALE: Record<string, number> = tokens.typography.scale_px;

/** Font weights. */
export const FONT_WEIGHTS: Record<string, number> = tokens.typography.weights;

/** Radius scale (px) — matches the Tailwind defaults the web compiles to. */
export const RADIUS: Record<string, number> = Object.fromEntries(
  Object.entries(tokens.radius).filter((entry): entry is [string, number] => typeof entry[1] === 'number'),
);

/** Spacing scale (px, 4px grid) + component paddings. */
export const SPACING: Record<string, number> = Object.fromEntries(
  Object.entries(tokens.spacing).filter((entry): entry is [string, number] => typeof entry[1] === 'number'),
);

/** Elevation scale. */
export const SHADOWS: Record<string, string> = tokens.shadow;

/** Motion durations (ms) + shared easing. */
export interface MotionSpec {
  fast_ms: number;
  base_ms: number;
  pulse_slow_ms: number;
  pulse_fast_ms: number;
  easing: string;
}

export const MOTION: MotionSpec = tokens.motion;

/** Focus ring width (px); ring color is ACCENT.primary. */
export const FOCUS_RING_WIDTH_PX: number = tokens.focus.ring_width_px;
