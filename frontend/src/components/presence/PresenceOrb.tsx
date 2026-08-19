import { motion, type TargetAndTransition } from 'framer-motion';
import { cn } from '../../utils/cn';
import type { PresenceStatus } from '../../types';

export interface PresenceOrbProps {
  status: PresenceStatus;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export function PresenceOrb({ status, size = 'lg', className }: PresenceOrbProps) {
  const sizeClasses = {
    sm: 'w-16 h-16',
    md: 'w-24 h-24',
    lg: 'w-32 h-32',
  };

  const statusColors = {
    idle: 'bg-presence-idle',
    working: 'bg-presence-working',
    listening: 'bg-presence-listening',
    speaking: 'bg-presence-speaking',
    offline: 'bg-background-surface',
  };

  const animationVariants: Record<PresenceStatus, TargetAndTransition> = {
    idle: {
      scale: [1, 1.05, 1],
      transition: { duration: 2, repeat: Infinity, ease: 'easeInOut' as const },
    },
    working: {
      scale: [1, 1.1, 1],
      transition: { duration: 1, repeat: Infinity, ease: 'easeInOut' as const },
    },
    listening: {
      scale: [1, 1.15, 1],
      transition: { duration: 1.5, repeat: Infinity, ease: 'easeInOut' as const },
    },
    speaking: {
      scale: [1, 1.12, 1],
      transition: { duration: 1.2, repeat: Infinity, ease: 'easeInOut' as const },
    },
    offline: {
      scale: 1,
    },
  };

  return (
    <motion.div
      className={cn(
        'rounded-full shadow-lg',
        sizeClasses[size],
        statusColors[status],
        className
      )}
      animate={animationVariants[status]}
    />
  );
}
