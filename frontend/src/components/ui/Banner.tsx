import { type ReactNode } from 'react';
import { AlertCircle, CheckCircle, Info, X } from 'lucide-react';
import { cn } from '../../utils/cn';

export interface BannerProps {
  type: 'info' | 'success' | 'warning' | 'error';
  children: ReactNode;
  onDismiss?: () => void;
  className?: string;
}

export function Banner({ type, children, onDismiss, className }: BannerProps) {
  const icons = {
    info: <Info className="w-5 h-5" />,
    success: <CheckCircle className="w-5 h-5" />,
    warning: <AlertCircle className="w-5 h-5" />,
    error: <AlertCircle className="w-5 h-5" />,
  };

  const colors = {
    info: 'bg-accent-primary/10 border-accent-primary text-accent-primary',
    success: 'bg-accent-success/10 border-accent-success text-accent-success',
    warning: 'bg-accent-warning/10 border-accent-warning text-accent-warning',
    error: 'bg-accent-error/10 border-accent-error text-accent-error',
  };

  return (
    <div
      className={cn(
        'flex items-start gap-3 p-4 rounded-lg border',
        colors[type],
        className
      )}
    >
      <div className="flex-shrink-0 mt-0.5">{icons[type]}</div>
      <div className="flex-1 text-sm">{children}</div>
      {onDismiss && (
        <button
          onClick={onDismiss}
          className="flex-shrink-0 p-1 rounded hover:bg-white/10 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      )}
    </div>
  );
}
