import { motion } from 'framer-motion';
import { cn } from '../../utils/cn';

interface AnimatedSpinnerProps {
  size?: 'sm' | 'md' | 'lg' | 'xl';
  className?: string;
}

export function AnimatedSpinner({ size = 'md', className }: AnimatedSpinnerProps) {
  const sizeMap = {
    sm: 'w-4 h-4',
    md: 'w-8 h-8',
    lg: 'w-12 h-12',
    xl: 'w-16 h-16',
  };

  return (
    <div className={cn('relative', sizeMap[size], className)}>
      <motion.div
        className="absolute inset-0 rounded-full border-2 border-background-surface"
      />
      <motion.div
        className="absolute inset-0 rounded-full border-2 border-transparent border-t-accent-primary"
        animate={{ rotate: 360 }}
        transition={{
          duration: 1,
          repeat: Infinity,
          ease: 'linear',
        }}
      />
    </div>
  );
}

interface PulseDotsProps {
  count?: number;
  className?: string;
}

export function PulseDots({ count = 3, className }: PulseDotsProps) {
  return (
    <div className={cn('flex items-center gap-1.5', className)}>
      {Array.from({ length: count }).map((_, i) => (
        <motion.div
          key={i}
          className="w-2 h-2 rounded-full bg-accent-primary"
          animate={{
            scale: [1, 1.3, 1],
            opacity: [0.5, 1, 0.5],
          }}
          transition={{
            duration: 1.2,
            repeat: Infinity,
            delay: i * 0.2,
            ease: 'easeInOut',
          }}
        />
      ))}
    </div>
  );
}

interface BouncingDotsProps {
  count?: number;
  className?: string;
}

export function BouncingDots({ count = 3, className }: BouncingDotsProps) {
  return (
    <div className={cn('flex items-center gap-1', className)}>
      {Array.from({ length: count }).map((_, i) => (
        <motion.div
          key={i}
          className="w-2 h-2 rounded-full bg-accent-primary"
          animate={{
            y: [-4, 4, -4],
          }}
          transition={{
            duration: 0.6,
            repeat: Infinity,
            delay: i * 0.1,
            ease: 'easeInOut',
          }}
        />
      ))}
    </div>
  );
}

interface SkeletonLoaderProps {
  className?: string;
  lines?: number;
}

export function SkeletonLoader({ className, lines = 3 }: SkeletonLoaderProps) {
  return (
    <div className={cn('space-y-3', className)}>
      {Array.from({ length: lines }).map((_, i) => (
        <motion.div
          key={i}
          className="h-4 bg-background-surface rounded overflow-hidden"
          style={{ width: `${100 - i * 10}%` }}
        >
          <motion.div
            className="h-full bg-gradient-to-r from-transparent via-background-surface/50 to-transparent"
            animate={{
              x: ['-100%', '200%'],
            }}
            transition={{
              duration: 1.5,
              repeat: Infinity,
              delay: i * 0.1,
              ease: 'easeInOut',
            }}
          />
        </motion.div>
      ))}
    </div>
  );
}

interface TypingIndicatorProps {
  className?: string;
}

export function TypingIndicator({ className }: TypingIndicatorProps) {
  return (
    <div className={cn('flex items-center gap-1 px-3 py-2', className)}>
      <motion.div
        className="w-2 h-2 rounded-full bg-text-muted"
        animate={{ y: [-2, 2, -2] }}
        transition={{ duration: 0.6, repeat: Infinity, delay: 0 }}
      />
      <motion.div
        className="w-2 h-2 rounded-full bg-text-muted"
        animate={{ y: [-2, 2, -2] }}
        transition={{ duration: 0.6, repeat: Infinity, delay: 0.15 }}
      />
      <motion.div
        className="w-2 h-2 rounded-full bg-text-muted"
        animate={{ y: [-2, 2, -2] }}
        transition={{ duration: 0.6, repeat: Infinity, delay: 0.3 }}
      />
    </div>
  );
}

interface ProgressBarProps {
  progress: number;
  className?: string;
}

export function ProgressBar({ progress, className }: ProgressBarProps) {
  return (
    <div className={cn('w-full h-2 bg-background-surface rounded-full overflow-hidden', className)}>
      <motion.div
        className="h-full bg-accent-primary rounded-full"
        initial={{ width: 0 }}
        animate={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
        transition={{ duration: 0.3, ease: 'easeOut' }}
      />
    </div>
  );
}
