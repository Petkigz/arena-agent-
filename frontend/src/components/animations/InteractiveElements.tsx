import { motion } from 'framer-motion';
import type { ReactNode, ButtonHTMLAttributes } from 'react';
import { buttonHoverVariants, cardHoverVariants } from './variants';
import { cn } from '../../utils/cn';

interface InteractiveButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  className?: string;
}

export function InteractiveButton({ children, className, disabled, ...props }: InteractiveButtonProps) {
  return (
    <motion.button
      whileHover={disabled ? undefined : 'hover'}
      whileTap={disabled ? undefined : 'tap'}
      variants={buttonHoverVariants}
      className={cn(
        'inline-flex items-center justify-center rounded-lg font-medium transition-colors duration-200',
        'focus:outline-none focus:ring-2 focus:ring-accent-primary focus:ring-offset-2 focus:ring-offset-background-primary',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        className
      )}
      disabled={disabled}
      {...(props as any)}
    >
      {children}
    </motion.button>
  );
}

interface InteractiveCardProps {
  children: ReactNode;
  className?: string;
  onClick?: () => void;
}

export function InteractiveCard({ children, className, onClick }: InteractiveCardProps) {
  return (
    <motion.div
      whileHover="hover"
      variants={cardHoverVariants}
      onClick={onClick}
      className={cn(
        'rounded-lg bg-background-secondary border border-background-surface p-4',
        'shadow-sm transition-shadow duration-200',
        onClick && 'cursor-pointer hover:shadow-md',
        className
      )}
    >
      {children}
    </motion.div>
  );
}
