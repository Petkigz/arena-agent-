import { type InputHTMLAttributes, forwardRef } from 'react';
import { cn } from '../../utils/cn';

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, error, ...props }, ref) => {
    return (
      <div className="w-full">
        {label && (
          <label className="block text-sm font-medium text-text-secondary mb-2">
            {label}
          </label>
        )}
        <input
          ref={ref}
          className={cn(
            'w-full px-4 py-2 rounded-lg',
            'bg-background-surface text-text-primary',
            'border border-border-subtle',
            'placeholder:text-text-muted',
            'focus:outline-none focus:ring-2 focus:ring-accent-primary focus:border-transparent',
            'transition-all duration-200',
            error && 'border-accent-error focus:ring-accent-error',
            className
          )}
          {...props}
        />
        {error && (
          <p className="mt-1 text-sm text-accent-error">{error}</p>
        )}
      </div>
    );
  }
);

Input.displayName = 'Input';
