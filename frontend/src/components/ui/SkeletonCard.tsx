import { Skeleton, SkeletonText } from './Skeleton';
import { cn } from '../../utils/cn';

export interface SkeletonCardProps {
  className?: string;
  lines?: number;
  showIcon?: boolean;
}

export function SkeletonCard({ className, lines = 3, showIcon = true }: SkeletonCardProps) {
  return (
    <div className={cn('p-4 bg-background-surface rounded-lg', className)}>
      <div className="flex items-start gap-3">
        {showIcon && <Skeleton className="w-10 h-10 rounded-lg flex-shrink-0" />}
        <div className="flex-1 space-y-2">
          <Skeleton className="h-5 w-3/4" />
          <SkeletonText lines={lines} />
        </div>
      </div>
    </div>
  );
}

export function SkeletonList({ items = 3, className }: { items?: number; className?: string }) {
  return (
    <div className={cn('space-y-3', className)}>
      {Array.from({ length: items }).map((_, i) => (
        <SkeletonCard key={i} lines={2} />
      ))}
    </div>
  );
}

export function SkeletonPage({ title = true, className }: { title?: boolean; className?: string }) {
  return (
    <div className={cn('space-y-6', className)}>
      {title && (
        <div className="space-y-2">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-4 w-64" />
        </div>
      )}
      <SkeletonList items={4} />
    </div>
  );
}

export function SkeletonForm({ fields = 4, className }: { fields?: number; className?: string }) {
  return (
    <div className={cn('space-y-4', className)}>
      {Array.from({ length: fields }).map((_, i) => (
        <div key={i} className="space-y-2">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-10 w-full" />
        </div>
      ))}
    </div>
  );
}
