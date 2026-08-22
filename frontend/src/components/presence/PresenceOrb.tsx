import { motion, type TargetAndTransition } from 'framer-motion';
import { cn } from '../../utils/cn';
import type { PresenceStatus } from '../../types';

export interface PresenceOrbProps {
  status: PresenceStatus;
  size?: 'xs' | 'sm' | 'md' | 'lg';
  className?: string;
  activity?: number;
}

const SIZE = { xs: 36, sm: 64, md: 112, lg: 180 } as const;

const STATUS_LABEL: Record<PresenceStatus, string> = {
  idle: 'Beanie is idle',
  working: 'Beanie is thinking or working',
  listening: 'Beanie is listening',
  speaking: 'Beanie is speaking',
  offline: 'Beanie is offline',
};

/** Beanie's living presence: core + ambient field + reactive interaction lines. */
export function PresenceOrb({ status, size = 'lg', className, activity = 0 }: PresenceOrbProps) {
  const px = SIZE[size];
  const normalizedActivity = Math.max(0, Math.min(1, activity));
  const active = status === 'listening' || status === 'speaking';
  const intensity = active ? Math.max(0.18, normalizedActivity) : status === 'working' ? 0.55 : 0.22;

  const coreAnimation: Record<PresenceStatus, TargetAndTransition> = {
    idle: { scale: [1, 1.035, 1], transition: { duration: 2.8, repeat: Infinity, ease: 'easeInOut' as const } },
    working: { scale: [1, 1.08, 1], rotate: [0, 3, -3, 0], transition: { duration: 1.8, repeat: Infinity, ease: 'easeInOut' as const } },
    listening: { scale: [1, 1.08 + intensity * 0.08, 1], transition: { duration: 0.7, repeat: Infinity, ease: 'easeInOut' as const } },
    speaking: { scale: [1, 1.1 + intensity * 0.1, 1], transition: { duration: 0.55, repeat: Infinity, ease: 'easeInOut' as const } },
    offline: { scale: 1, opacity: 0.45 },
  };

  const lineCount = size === 'xs' ? 8 : size === 'sm' ? 10 : 14;
  const lines = Array.from({ length: lineCount }, (_, index) => {
    const angle = (360 / lineCount) * index;
    const length = px * (0.13 + ((index * 17) % 7) * 0.012);
    return { angle, length };
  });

  return (
    <div
      className={cn('relative flex items-center justify-center select-none', className)}
      style={{ width: px * 1.8, height: px * 1.8 }}
      role="img"
      aria-label={STATUS_LABEL[status]}
    >
      <motion.div
        className="absolute rounded-full pointer-events-none"
        style={{ width: px * 1.55, height: px * 1.55, background: 'radial-gradient(circle, rgba(59,130,246,.24) 0%, rgba(139,92,246,.10) 42%, transparent 72%)', filter: 'blur(7px)' }}
        animate={{ scale: status === 'offline' ? 1 : [0.94, 1.08 + intensity * 0.1, 0.94], opacity: status === 'offline' ? 0.25 : [0.55, 0.9, 0.55] }}
        transition={{ duration: active ? 1.2 : 2.8, repeat: Infinity, ease: 'easeInOut' }}
      />

      <motion.svg
        className="absolute inset-0 w-full h-full pointer-events-none overflow-visible text-blue-400"
        viewBox="0 0 100 100"
        animate={status === 'working' ? { rotate: [0, 360] } : status === 'listening' ? { rotate: [0, -360] } : { rotate: 0 }}
        transition={{ duration: status === 'working' ? 12 : 18, repeat: Infinity, ease: 'linear' }}
        aria-hidden="true"
      >
        {lines.map(({ angle, length }, index) => {
          const rad = (angle * Math.PI) / 180;
          const inner = 30;
          const outer = inner + (length / px) * 100 * (1 + intensity * 1.8);
          return (
            <motion.line
              key={index}
              x1={50 + Math.cos(rad) * inner}
              y1={50 + Math.sin(rad) * inner}
              x2={50 + Math.cos(rad) * outer}
              y2={50 + Math.sin(rad) * outer}
              stroke="currentColor"
              strokeWidth={size === 'xs' ? 0.7 : 0.9}
              strokeLinecap="round"
              animate={active ? { opacity: [0.18, 0.9, 0.22], scale: [0.8, 1 + intensity, 0.8] } : status === 'working' ? { opacity: [0.2, 0.7, 0.2] } : { opacity: [0.12, 0.32, 0.12] }}
              transition={{ duration: active ? 0.5 + (index % 4) * 0.12 : status === 'working' ? 1.4 : 2.8, repeat: Infinity, delay: index * 0.055, ease: 'easeInOut' }}
              style={{ transformOrigin: '50px 50px' }}
            />
          );
        })}
        <motion.circle
          cx="50" cy="50" r="34" fill="none" stroke="currentColor" strokeWidth="0.55"
          animate={{ r: active ? [31, 38 + intensity * 5, 31] : [33, 35, 33], opacity: [0.2, 0.55, 0.2] }}
          transition={{ duration: active ? 0.8 : 2.6, repeat: Infinity, ease: 'easeInOut' }}
        />
      </motion.svg>

      <motion.div
        className={cn('relative rounded-full flex items-center justify-center overflow-hidden border border-white/20', size === 'xs' ? 'w-7 h-7' : size === 'sm' ? 'w-12 h-12' : size === 'md' ? 'w-20 h-20' : 'w-32 h-32')}
        style={{ background: 'radial-gradient(circle at 38% 32%, rgba(255,255,255,.65), rgba(96,165,250,.42) 18%, rgba(37,99,235,.35) 42%, rgba(15,23,42,.92) 76%)', boxShadow: '0 0 24px rgba(59,130,246,.28), inset 0 0 22px rgba(255,255,255,.08)' }}
        animate={coreAnimation[status]}
      >
        <motion.div
          className="absolute rounded-full bg-white/60 blur-[2px]"
          style={{ width: px * 0.08, height: px * 0.08, left: '31%', top: '26%' }}
          animate={{ opacity: status === 'offline' ? 0.15 : [0.35, 0.9, 0.35] }}
          transition={{ duration: active ? 0.7 : 2.4, repeat: Infinity }}
        />
        <motion.div
          className="rounded-full bg-white/75"
          style={{ width: Math.max(3, px * 0.025), height: Math.max(3, px * 0.025), boxShadow: '0 0 12px rgba(255,255,255,.8)' }}
          animate={active ? { scale: [1, 1 + intensity, 1] } : { scale: [1, 1.06, 1] }}
          transition={{ duration: active ? 0.45 : 2.2, repeat: Infinity }}
        />
      </motion.div>
    </div>
  );
}
