import { useEffect, useId, useRef } from 'react';
import { cn } from '../../utils/cn';
import { BEANIE_STATES, type BeanieOrbStatus } from '../../design/tokens';

export type { BeanieOrbStatus };

/**
 * Extended cognitive/voice states beyond the wire `PresenceStatus`. The orb is
 * Beanie's *presence* — not an avatar — so it carries a richer visual language:
 * idle breathing, listening (mic-reactive), thinking (circulating), acting
 * (directional sweep), observing (scan), speaking (outward TTS waves), success
 * (ripple), error (disturbance), sleeping (dim).
 *
 * Colors come from the shared design system (design/tokens.json) — the same
 * file the desktop client reads — so the presence palette cannot drift.
 */

// Base radii in the 120×120 viewBox (center 60,60). Core sits inside ring 0.
const CORE_R = 24;
const RING_RADII = [32, 41, 50];

type Size = 'sm' | 'md' | 'lg';

const SIZE_CLASSES: Record<Size, string> = {
  sm: 'w-8 h-8',
  md: 'w-24 h-24',
  lg: 'w-32 h-32',
};

interface ReactiveBeanieOrbProps {
  status?: BeanieOrbStatus;
  /** 0..1 — microphone (listening) or TTS (speaking) amplitude. */
  level?: number;
  size?: Size;
  /** Hide the voice-field rings (tiny avatar contexts). Defaults to size !== 'sm'. */
  showField?: boolean;
  className?: string;
}

/**
 * ReactiveBeanieOrb — a layered translucent core wrapped in a voice field.
 *
 * Two motion channels, kept orthogonal so they never fight:
 * - CSS keyframes own `transform` + `opacity` (the per-state character).
 * - A requestAnimationFrame loop owns only `r` (ring radius) so the field
 *   visibly expands/contracts with live mic/TTS amplitude when listening or
 *   speaking — no React re-render per frame.
 */
export function ReactiveBeanieOrb({
  status = 'idle',
  level = 0,
  size = 'lg',
  showField,
  className,
}: ReactiveBeanieOrbProps) {
  const gradCore = 'core-' + useId().replace(/[^a-zA-Z0-9_-]/g, '');
  const gradHalo = 'halo-' + useId().replace(/[^a-zA-Z0-9_-]/g, '');

  const color = BEANIE_STATES[status]?.color ?? BEANIE_STATES.idle.color;
  const full = showField ?? size !== 'sm';

  const levelRef = useRef(level);
  const smoothRef = useRef(0);
  const ringRefs = useRef<(SVGCircleElement | null)[]>([]);
  const rafRef = useRef<number | null>(null);

  levelRef.current = level;

  // Amplitude loop — radius only. Smooths `level` and writes `r` to the rings.
  useEffect(() => {
    if (!full) return;
    const reactive = status === 'listening' || status === 'speaking';

    const tick = () => {
      if (reactive) {
        smoothRef.current += (clamp01(levelRef.current) - smoothRef.current) * 0.22;
        const l = smoothRef.current;
        ringRefs.current.forEach((el, i) => {
          if (!el) return;
          const amp = l * 7 * (1 - i * 0.18);
          el.setAttribute('r', String(Math.max(1, RING_RADII[i] + amp)));
        });
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [full, status]);

  const coreAnim = coreAnimation(status);
  const ringAnim = ringAnimation(status);
  const ringDash = ringDasharray(status);

  return (
    <div
      className={cn('relative', SIZE_CLASSES[size], className)}
      role="img"
      aria-label={`Beanie presence — ${status}`}
    >
      <svg viewBox="0 0 120 120" className="w-full h-full" aria-hidden="true">
        <defs>
          <radialGradient id={gradHalo} cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor={color} stopOpacity="0.32" />
            <stop offset="70%" stopColor={color} stopOpacity="0.1" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </radialGradient>
          <radialGradient id={gradCore} cx="38%" cy="32%" r="75%">
            <stop offset="0%" stopColor="#ffffff" stopOpacity="0.9" />
            <stop offset="28%" stopColor={color} stopOpacity="0.55" />
            <stop offset="72%" stopColor={color} stopOpacity="0.28" />
            <stop offset="100%" stopColor={color} stopOpacity="0.08" />
          </radialGradient>
        </defs>

        {/* Soft outer halo */}
        {full && (
          <circle
            className="beanie-orb__halo"
            cx="60"
            cy="60"
            r="54"
            fill={`url(#${gradHalo})`}
          />
        )}

        {/* Voice field — reactive rings */}
        {full &&
          RING_RADII.map((r, i) => {
            const anim = ringAnim ? ringAnim.rings[i % ringAnim.rings.length] : undefined;
            return (
              <circle
                key={i}
                ref={(el) => {
                  ringRefs.current[i] = el;
                }}
                className="beanie-orb__ring"
                cx="60"
                cy="60"
                r={r}
                fill="none"
                stroke={color}
                strokeWidth={1.1}
                strokeLinecap="round"
                strokeDasharray={ringDash}
                opacity={status === 'offline' || status === 'sleeping' ? 0 : 0.35}
                style={{
                  animation: anim,
                  animationDelay: anim && status === 'speaking' ? `${i * 0.16}s` : undefined,
                }}
              />
            );
          })}

        {/* Core sphere */}
        <circle
          className="beanie-orb__core"
          cx="60"
          cy="60"
          r={CORE_R}
          fill={`url(#${gradCore})`}
          stroke={color}
          strokeOpacity="0.55"
          strokeWidth="1.2"
          style={{ animation: coreAnim }}
        />

        {/* Inner highlight (light diffusion, not a face) */}
        <circle cx="51" cy="49" r="8" fill="#ffffff" opacity="0.32" />

        {/* Focal point — presence, always subtle */}
        <circle
          className="beanie-orb__focus"
          cx="60"
          cy="60"
          r="3.6"
          fill={color}
          style={{
            animation:
              status === 'offline' || status === 'sleeping'
                ? undefined
                : 'beanie-focus 3s ease-in-out infinite',
          }}
        />
      </svg>
    </div>
  );
}

function clamp01(n: number): number {
  return n <= 0 ? 0 : n >= 1 ? 1 : n;
}

/** Core (sphere) animation per state. */
function coreAnimation(status: BeanieOrbStatus): string | undefined {
  switch (status) {
    case 'idle':
      return 'beanie-breathe 3.4s ease-in-out infinite';
    case 'sleeping':
      return 'beanie-breathe 5s ease-in-out infinite';
    case 'listening':
      return 'beanie-breathe-fast 1.2s ease-in-out infinite';
    case 'speaking':
      return 'beanie-breathe-fast 1.05s ease-in-out infinite';
    case 'working':
    case 'thinking':
      return 'beanie-breathe-fast 1.6s ease-in-out infinite';
    case 'acting':
    case 'observing':
      return 'beanie-breathe-fast 2s ease-in-out infinite';
    case 'error':
      return 'beanie-disturb 0.4s ease-in-out infinite';
    case 'success':
      return 'beanie-breathe 2s ease-in-out infinite';
    case 'offline':
      return undefined;
    default:
      return 'beanie-breathe 3.4s ease-in-out infinite';
  }
}

/** Per-ring animation strings, keyed by state. */
function ringAnimation(
  status: BeanieOrbStatus
): { rings: string[] } | undefined {
  switch (status) {
    case 'idle':
      return { rings: ['beanie-ring-pulse 3.2s ease-in-out infinite'] };
    case 'listening':
      // Radius is amplitude-driven (rAF); this pulse is the silent baseline.
      return { rings: ['beanie-ring-pulse 2s ease-in-out infinite'] };
    case 'speaking':
      return {
        rings: [
          'beanie-outward 1.35s ease-out infinite',
          'beanie-outward 1.35s ease-out infinite',
          'beanie-outward 1.35s ease-out infinite',
        ],
      };
    case 'thinking':
      return {
        rings: [
          'beanie-spin 7s linear infinite',
          'beanie-spin-reverse 9s linear infinite',
          'beanie-spin 11s linear infinite',
        ],
      };
    case 'working':
      return { rings: ['beanie-ring-pulse 1.4s ease-in-out infinite'] };
    case 'acting':
      return {
        rings: [
          'beanie-spin 3.2s linear infinite',
          'beanie-spin 5s linear infinite',
          'beanie-spin 7s linear infinite',
        ],
      };
    case 'observing':
      return {
        rings: ['beanie-spin 4s linear infinite', 'beanie-spin-reverse 6s linear infinite'],
      };
    case 'success':
      return {
        rings: [
          'beanie-ripple 0.85s ease-out infinite',
          'beanie-ripple 0.85s ease-out infinite',
          'beanie-ripple 0.85s ease-out infinite',
        ],
      };
    case 'error':
      return { rings: ['beanie-disturb 0.4s ease-in-out infinite'] };
    case 'sleeping':
    case 'offline':
    default:
      return undefined;
  }
}

/** Dash pattern per state — visible arc segments give the "voice lines" look. */
function ringDasharray(status: BeanieOrbStatus): string | undefined {
  switch (status) {
    case 'thinking':
    case 'acting':
    case 'observing':
      return '30 22'; // rotation must be visible → segmented arcs
    case 'speaking':
      return '46 20'; // longer outward waves
    case 'idle':
    case 'listening':
    case 'working':
      return '24 16';
    case 'success':
    case 'error':
      return '34 20';
    default:
      return undefined;
  }
}
