import { type ReactNode, type HTMLAttributes } from 'react';
import { motion } from 'framer-motion';
import { cn } from '../../utils/cn';
import { cardHoverVariants } from '../animations/variants';

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  className?: string;
  padding?: 'none' | 'sm' | 'md' | 'lg';
  interactive?: boolean;
}

export function Card({ children, className, padding = 'md', interactive = false, ...props }: CardProps) {
  const Component = interactive ? motion.div : 'div';
  
  return (
    <Component
      {...(interactive ? { whileHover: 'hover', variants: cardHoverVariants } : {})}
      className={cn(
        'rounded-lg bg-background-surface border border-border-subtle',
        'transition-shadow duration-200',
        interactive && 'cursor-pointer hover:shadow-lg',
        {
          'p-0': padding === 'none',
          'p-3': padding === 'sm',
          'p-4': padding === 'md',
          'p-6': padding === 'lg',
        },
        className
      )}
      {...(props as any)}
    >
      {children}
    </Component>
  );
}
